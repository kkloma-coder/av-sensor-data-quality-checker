# -*- coding: utf-8 -*-
"""
generate_sample_data.py
------------------------
作用：生成一份模拟的自动驾驶车辆传感器运行日志（CSV格式）。

为什么要自己生成数据而不是用真实数据集？
- 真实的自动驾驶数据集（如 nuScenes）体积大、格式复杂，短时间内不适合作为练手项目。
- 这里用脚本模拟一份"结构上接近真实车辆日志"的数据：
  包含时间戳、车速、与前车距离、GPS坐标、传感器状态等字段。
- 关键是：我们会【故意】在数据里插入几类常见问题（缺失值、超范围异常值、
  时间戳跳变/乱序、重复行），这样下一步的 data_quality_checker.py
  才有"真实问题"可以检测出来，而不是检测一份完美无缺的数据（那样就没有意义了）。

运行方式：
    python3 generate_sample_data.py
会在当前目录生成 sensor_log.csv
"""

import pandas as pd
import numpy as np

# 固定随机种子，保证每次生成的数据一致，方便复现和讲解
np.random.seed(42)

N = 2000  # 模拟2000条传感器记录

# 1. 生成基础时间戳序列：假设每0.1秒采集一次数据（10Hz，接近真实车载传感器频率）
base_timestamps = pd.date_range("2026-01-01 08:00:00", periods=N, freq="100ms")
timestamps = list(base_timestamps)

# 2. 生成正常范围内的车速数据（单位：km/h），城市道路场景，均值40，标准差15
speed = np.random.normal(loc=40, scale=15, size=N)

# 3. 生成与前车距离数据（单位：米），均值20米，标准差8米
distance_to_obstacle = np.random.normal(loc=20, scale=8, size=N)

# 4. 生成GPS经纬度（模拟车辆在小范围内移动，数值仅用于结构完整性，非真实道路）
lat = 39.9042 + np.cumsum(np.random.normal(0, 0.00002, size=N))
lon = 116.4074 + np.cumsum(np.random.normal(0, 0.00002, size=N))

# 5. 传感器状态字段：normal / warning / error，绝大多数应为 normal
sensor_status = np.random.choice(
    ["normal", "warning", "error"], size=N, p=[0.95, 0.04, 0.01]
)

df = pd.DataFrame({
    "timestamp": timestamps,
    "speed_kmh": speed,
    "distance_to_obstacle_m": distance_to_obstacle,
    "gps_lat": lat,
    "gps_lon": lon,
    "sensor_status": sensor_status,
})

# ============================================================
# 下面开始【故意注入问题】，模拟真实传感器日志里常见的脏数据情况
# ============================================================

# 问题1：缺失值 —— 随机让约2%的车速数据变成 NaN（模拟传感器瞬时丢帧）
missing_idx = np.random.choice(df.index, size=int(N * 0.02), replace=False)
df.loc[missing_idx, "speed_kmh"] = np.nan

# 问题2：超范围异常值 —— 车速不可能是负数或超过200km/h，故意插入几条明显错误的数值
# 这类问题在真实场景中，往往是传感器故障或单位换算错误导致的
outlier_idx = np.random.choice(df.index, size=15, replace=False)
df.loc[outlier_idx[:8], "speed_kmh"] = np.random.uniform(250, 400, size=8)   # 明显超速异常
df.loc[outlier_idx[8:], "speed_kmh"] = np.random.uniform(-50, -1, size=7)    # 负数异常

# 问题3：与前车距离出现负数（物理上不可能，通常是传感器噪声或标定错误）
dist_outlier_idx = np.random.choice(df.index, size=10, replace=False)
df.loc[dist_outlier_idx, "distance_to_obstacle_m"] = np.random.uniform(-10, -1, size=10)

# 问题4：时间戳跳变 —— 模拟传感器某段时间"卡顿"，导致时间戳出现较大跳跃间隔
# 真实车辆日志中，这类问题会导致后续基于时间序列的分析（如速度变化率计算）出错
jump_points = np.random.choice(range(100, N - 100), size=5, replace=False)
for jp in jump_points:
    # 人为制造一个 2~5 秒的时间跳跃
    jump_seconds = np.random.uniform(2, 5)
    for i in range(jp, N):
        timestamps[i] = timestamps[i] + pd.Timedelta(seconds=jump_seconds)
df["timestamp"] = timestamps

# 问题5：重复记录 —— 模拟日志系统偶尔重复写入同一条记录
dup_rows = df.sample(n=6, random_state=1)
df = pd.concat([df, dup_rows], ignore_index=True)

# 保存为 CSV
output_path = "sensor_log.csv"
df.to_csv(output_path, index=False, encoding="utf-8-sig")

print(f"已生成模拟传感器日志：{output_path}，共 {len(df)} 条记录")
print("已注入问题：缺失值、超范围异常值、负数异常、时间戳跳变、重复记录")
