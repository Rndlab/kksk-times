import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import re

def normalize_content(content, keyword):
    # 处理问号弹幕的匹配优化
    if any(c in keyword for c in ['？', '?']):
        # 将中文问号转为英文问号，并去除重复问号
        content = re.sub(r'[？?]+', '?', content)
    return content

def should_match(content, keyword):
    """执行模糊匹配判断"""
    # 预处理内容
    processed_content = normalize_content(content, keyword)
    
    # 生成匹配模式
    if keyword in ['？', '?'] or set(keyword) <= {'？', '?'}:
        # 问号匹配模式：允许任意数量问号组合
        pattern = r'^\?+$'
        return bool(re.match(pattern, processed_content))
    elif keyword.isalpha():
        # 字母关键词：不区分大小写
        return processed_content.lower() == keyword.lower()
    return processed_content == keyword

def parse_timestamps(folder_path, keyword):
    """
    解析所有XML文件，提取指定关键词弹幕的时间戳和来源文件，
    同时额外保存第一条弹幕的p属性的第一个数据（一般为视频内秒数）
    """
    times = []
    
    for filename in os.listdir(folder_path):
        if not filename.endswith('.xml'):
            continue
            
        file_path = os.path.join(folder_path, filename)
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except Exception as e:
            print(f"解析失败 {filename}: {str(e)}")
            continue

        for elem in root.findall('.//d'):
            raw_content = elem.text.strip() if elem.text else ''
            content = normalize_content(raw_content, keyword)
            
            if not should_match(content, keyword):
                continue

            p_attr = elem.get('p', '')
            attrs = p_attr.split(',')
            if len(attrs) < 5:
                continue

            try:
                timestamp = int(attrs[4])
                # 提取p属性的第一个数据，通常为视频播放时长（秒数）
                first_p = attrs[0]
                times.append((timestamp, filename, first_p))
            except ValueError:
                continue

    # 按时间戳排序
    times.sort(key=lambda x: x[0])
    return times

def find_peak_windows(times, window_sec=60):
    """寻找最密集的时间窗口"""
    window_ms = window_sec * 1000
    windows = []

    # 使用滑动窗口计算密度
    left = 0
    for right in range(len(times)):
        # 移动左指针
        while times[right][0] - times[left][0] > window_ms:
            left += 1
        
        # 统计当前窗口内的弹幕数量
        count = right - left + 1
        if count > 0:
            # 记录窗口信息和来源文件统计
            source_files = defaultdict(int)
            for i in range(left, right + 1):
                source_files[times[i][1]] += 1
            
            # 保存窗口中第一条弹幕的p属性第一个数据（视频内秒数）
            first_video_time = times[left][2]
            
            windows.append({
                'count': count,
                'start': times[left][0],
                'end': times[right][0],
                'sources': source_files,
                'first_video_time': first_video_time
            })

    # 按密度（弹幕数量）排序
    windows.sort(reverse=True, key=lambda x: x['count'])
    
    # 选择非重叠的Top10窗口
    selected = []
    for win in windows:
        overlap = False
        for selected_win in selected:
            if win['start'] < selected_win['end'] and win['end'] > selected_win['start']:
                overlap = True
                break
        if not overlap:
            selected.append(win)
            if len(selected) >= 10:
                break

    return selected

def convert_seconds_to_hms(seconds_val):
    """将秒数转换为时:分:秒格式"""
    try:
        seconds_val = float(seconds_val)
    except ValueError:
        return "Invalid"
    hours = int(seconds_val // 3600)
    minutes = int((seconds_val % 3600) // 60)
    seconds = int(seconds_val % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def format_result(selected_windows, keyword):
    """格式化输出结果"""
    results = []
    for idx, win in enumerate(selected_windows[:10], 1):
        # 计算密集窗口的中点时间（东八区）
        midpoint = (win['start'] + win['end']) // 2
        dt = datetime.fromtimestamp(midpoint / 1000, tz=timezone.utc) + timedelta(hours=8)
        formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S CST')

        # 转换第一条弹幕p属性的第一个秒数为时分秒格式
        first_comment_hms = convert_seconds_to_hms(win['first_video_time'])

        # 处理来源文件信息
        source_files = sorted(win['sources'].items(), key=lambda x: x[1], reverse=True)
        source_info = "\n       ".join([f"{fname} ({count}条)" for fname, count in source_files])

        results.append({
            'rank': idx,
            'time': formatted_time,
            'count': win['count'],
            'start': win['start'],
            'end': win['end'],
            'sources': source_info,
            'first_comment_video_time': first_comment_hms  # 新增输出参数
        })
    return results

if __name__ == "__main__":
    # 配置参数
    CONFIG = {
        'folder_path': "./xml",           # XML文件夹路径
        'keyword': "kksk",                # 要分析的弹幕关键词，也可以用 “两眼一黑”、“？” 等查找特定时刻
        'window_sec': 60                 # 检测窗口大小（秒）
    }

    print(f"正在分析弹幕关键词: {CONFIG['keyword']}")
    
    # 处理流程
    print("正在解析XML文件...")
    timestamps = parse_timestamps(CONFIG['folder_path'], CONFIG['keyword'])
    if not timestamps:
        print(f"未找到'{CONFIG['keyword']}'弹幕数据")
    else:
        print("正在分析弹幕密度...")
        peaks = find_peak_windows(timestamps, CONFIG['window_sec'])
        results = format_result(peaks, CONFIG['keyword'])

        # 打印结果
        print(f"\nTop10 '{CONFIG['keyword']}'弹幕密集时刻（{CONFIG['window_sec']}秒窗口）:")
        for item in results:
            print(f"\n{item['rank']}. {item['time']}")
            print(f"   弹幕数量: {item['count']}条")
            print(f"   时间范围: {item['start']} - {item['end']}")
            print(f"   来源文件:\n       {item['sources']}")
            print(f"   第一条弹幕视频时间: {item['first_comment_video_time']}")
            print("-" * 80)
