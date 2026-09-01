# -*- coding: utf-8 -*-
"""
data_quality_checker.py
------------------------
作用：对车辆传感器运行日志（CSV）进行数据质量检测，输出结构化报告。

这个脚本对应的能力点（面试/简历里要能讲清楚的）：
1. 缺失值检测 —— 逐字段统计缺失数量与占比
2. 超范围/物理不合理值检测 —— 基于业务常识设定合理阈值（比如车速不可能为负）
3. 时间戳连续性检测 —— 检测采样间隔是否稳定，是否存在跳变或乱序
4. 重复记录检测 —— 识别完全重复的行
5. 结果输出 —— 生成 Markdown 格式的质量报告 + 一张可视化图表

设计思路（面试时可以这样讲）：
- 每一类检测都封装成一个独立函数，输入是 DataFrame，输出是"发现的问题列表 + 统计数字"。
  这样做的好处是：以后要新增检测规则（比如加一个GPS跳变检测），
  只需要新增一个函数并注册到 CHECKS 列表里，不需要改动其他逻辑——这是简单的可扩展设计。
- 阈值（比如车速上限200km/h）不是随便拍的，而是基于常识合理性设定：
  城市/高速场景下车速一般不会超过 150-180 km/h，这里留了一些余量取 200 作为报警线。
  真实项目中，这类阈值应该由业务方（车辆工程/测试团队）提供标准，而不是工程师自己拍脑袋定。

运行方式：
    python3 data_quality_checker.py
需要先运行 generate_sample_data.py 生成 sensor_log.csv
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # 服务器/无界面环境下渲染图片
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ------------------------------------------------------------------
# 中文字体处理：避免图表里中文显示为方块
# ------------------------------------------------------------------
plt.rcParams["axes.unicode_minus"] = False
for font_name in ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei", "Microsoft YaHei"]:
    if any(font_name.lower() in f.name.lower() for f in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [font_name]
        break


# ============================================================
# 各类质量检测函数
# ============================================================

def check_missing_values(df: pd.DataFrame) -> dict:
    """检测每个字段的缺失值数量和占比"""
    missing_count = df.isna().sum()
    missing_ratio = (missing_count / len(df) * 100).round(2)
    result = {
        col: {"缺失数量": int(missing_count[col]), "缺失占比(%)": float(missing_ratio[col])}
        for col in df.columns if missing_count[col] > 0
    }
    return result


def check_out_of_range(df: pd.DataFrame) -> dict:
    """
    检测超出物理合理范围的数值。
    这里的阈值是基于常识设定的示例值，真实项目中应替换为业务方给定的标准。
    """
    rules = {
        "speed_kmh": (0, 200),                  # 车速：不应为负，也不应超过200km/h
        "distance_to_obstacle_m": (0, 500),     # 与前车距离：不应为负
    }
    result = {}
    for col, (low, high) in rules.items():
        if col not in df.columns:
            continue
        # 注意：先剔除 NaN 再判断范围，避免和缺失值检测的问题混在一起统计
        valid = df[col].dropna()
        violations = valid[(valid < low) | (valid > high)]
        if len(violations) > 0:
            result[col] = {
                "合理范围": f"[{low}, {high}]",
                "违规数量": int(len(violations)),
                "违规示例(最多5条)": violations.head(5).tolist(),
            }
    return result


def check_timestamp_continuity(df: pd.DataFrame, expected_interval_ms=100, tolerance_ms=50) -> dict:
    """
    检测时间戳连续性：
    - 计算相邻时间戳的间隔
    - 如果间隔明显大于预期采样间隔（比如设计上是10Hz/100ms一条），标记为"跳变"
    - 如果出现时间戳倒退（乱序），单独标记
    """
    ts = pd.to_datetime(df["timestamp"])
    diffs_ms = ts.diff().dt.total_seconds() * 1000  # 转成毫秒

    jumps = diffs_ms[diffs_ms > (expected_interval_ms + tolerance_ms)]
    reversed_ts = diffs_ms[diffs_ms < 0]

    return {
        "预期采样间隔(ms)": expected_interval_ms,
        "检测到的时间跳变次数": int(len(jumps)),
        "最大跳变间隔(ms)": float(jumps.max()) if len(jumps) > 0 else 0,
        "时间戳倒退(乱序)次数": int(len(reversed_ts)),
    }


def check_duplicates(df: pd.DataFrame) -> dict:
    """检测完全重复的记录行"""
    dup_count = int(df.duplicated().sum())
    return {"重复记录数量": dup_count}


# ============================================================
# 汇总执行 + 生成报告
# ============================================================

def run_all_checks(csv_path: str):
    df = pd.read_csv(csv_path)

    results = {
        "缺失值检测": check_missing_values(df),
        "超范围异常值检测": check_out_of_range(df),
        "时间戳连续性检测": check_timestamp_continuity(df),
        "重复记录检测": check_duplicates(df),
    }
    return df, results


def write_markdown_report(results: dict, total_rows: int, report_path="quality_report.md"):
    lines = []
    lines.append("# 传感器日志数据质量检测报告\n")
    lines.append(f"- 总记录数：{total_rows}\n")

    lines.append("## 1. 缺失值检测\n")
    if results["缺失值检测"]:
        lines.append("| 字段 | 缺失数量 | 缺失占比(%) |")
        lines.append("|---|---|---|")
        for col, info in results["缺失值检测"].items():
            lines.append(f"| {col} | {info['缺失数量']} | {info['缺失占比(%)']} |")
    else:
        lines.append("未发现缺失值。")
    lines.append("")

    lines.append("## 2. 超范围异常值检测\n")
    if results["超范围异常值检测"]:
        for col, info in results["超范围异常值检测"].items():
            lines.append(f"- **{col}**：合理范围 {info['合理范围']}，违规 {info['违规数量']} 条")
            lines.append(f"  - 违规示例：{info['违规示例(最多5条)']}")
    else:
        lines.append("未发现超范围异常值。")
    lines.append("")

    lines.append("## 3. 时间戳连续性检测\n")
    tc = results["时间戳连续性检测"]
    lines.append(f"- 预期采样间隔：{tc['预期采样间隔(ms)']} ms")
    lines.append(f"- 检测到时间跳变次数：{tc['检测到的时间跳变次数']}")
    lines.append(f"- 最大跳变间隔：{tc['最大跳变间隔(ms)']} ms")
    lines.append(f"- 时间戳倒退(乱序)次数：{tc['时间戳倒退(乱序)次数']}")
    lines.append("")

    lines.append("## 4. 重复记录检测\n")
    lines.append(f"- 重复记录数量：{results['重复记录检测']['重复记录数量']}")
    lines.append("")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"质量报告已生成：{report_path}")


def plot_summary_chart(results: dict, total_rows: int, chart_path="quality_summary.png"):
    """生成一张汇总柱状图，展示各类问题的数量，用于直观展示检测结果"""
    missing_total = sum(v["缺失数量"] for v in results["缺失值检测"].values())
    outlier_total = sum(v["违规数量"] for v in results["超范围异常值检测"].values())
    jump_total = results["时间戳连续性检测"]["检测到的时间跳变次数"]
    dup_total = results["重复记录检测"]["重复记录数量"]

    categories = ["缺失值", "超范围异常值", "时间戳跳变", "重复记录"]
    counts = [missing_total, outlier_total, jump_total, dup_total]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(categories, counts, color=["#4C72B0", "#DD8452", "#55A868", "#C44E52"])
    ax.set_title(f"数据质量检测结果汇总（总记录数 {total_rows}）")
    ax.set_ylabel("问题数量")
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                str(count), ha="center", va="bottom")
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    print(f"汇总图表已生成：{chart_path}")


if __name__ == "__main__":
    df, results = run_all_checks("sensor_log.csv")
    write_markdown_report(results, total_rows=len(df))
    plot_summary_chart(results, total_rows=len(df))

    print("\n===== 检测结果概览 =====")
    for section, content in results.items():
        print(f"\n[{section}]")
        print(content)
