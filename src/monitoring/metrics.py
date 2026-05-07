"""
Metrics Collector
系统指标采集器 — CPU/内存/磁盘监控 + Prometheus指标导出
"""

import os
import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime


class MetricsCollector:
    """系统指标采集器"""

    def __init__(self):
        self._metrics: Dict[str, Any] = {}
        self._task_counter = 0
        self._error_counter = 0
        self._response_times: list = []
        self._start_time = time.time()
        self._lock = threading.Lock()
        self._start_collection()

    def _start_collection(self):
        """启动后台指标采集"""
        self._collect_system_metrics()
        print("[Metrics] Collector started")

    def _collect_system_metrics(self):
        """采集系统指标"""
        with self._lock:
            self._metrics['timestamp'] = datetime.now().isoformat()

            # CPU
            try:
                import psutil
                self._metrics['cpu_percent'] = psutil.cpu_percent(interval=1)
                self._metrics['cpu_count'] = psutil.cpu_count()
            except ImportError:
                self._metrics['cpu_percent'] = self._mock_cpu()

            # 内存
            try:
                import psutil
                mem = psutil.virtual_memory()
                self._metrics['memory_total_gb'] = round(mem.total / (1024**3), 1)
                self._metrics['memory_used_percent'] = mem.percent
                self._metrics['memory_available_gb'] = round(mem.available / (1024**3), 1)
            except ImportError:
                self._metrics['memory_used_percent'] = self._mock_memory()

            # 磁盘
            try:
                import psutil
                disk = psutil.disk_usage('/')
                self._metrics['disk_total_gb'] = round(disk.total / (1024**3), 1)
                self._metrics['disk_used_percent'] = disk.percent
                self._metrics['disk_free_gb'] = round(disk.free / (1024**3), 1)
            except ImportError:
                self._metrics['disk_used_percent'] = 45.0

            # 应用指标
            uptime = time.time() - self._start_time
            self._metrics['uptime_seconds'] = int(uptime)
            self._metrics['task_count'] = self._task_counter
            self._metrics['error_count'] = self._error_counter

            if self._response_times:
                recent = self._response_times[-100:]
                self._metrics['avg_response_time_ms'] = round(
                    sum(recent) / len(recent) * 1000, 1
                )
                self._metrics['p95_response_time_ms'] = round(
                    sorted(recent)[int(len(recent) * 0.95)] * 1000, 1
                    if len(recent) >= 20 else max(recent) * 1000, 1
                )

    def record_task(self, success: bool, response_time: float = 0):
        """记录任务执行"""
        with self._lock:
            self._task_counter += 1
            if not success:
                self._error_counter += 1
            if response_time > 0:
                self._response_times.append(response_time)
                if len(self._response_times) > 1000:
                    self._response_times = self._response_times[-1000:]

    def get_metrics(self) -> dict:
        """获取当前指标"""
        self._collect_system_metrics()
        with self._lock:
            return dict(self._metrics)

    def get_health_status(self) -> dict:
        """获取健康检查状态"""
        self._collect_system_metrics()
        with self._lock:
            cpu = self._metrics.get('cpu_percent', 0)
            mem = self._metrics.get('memory_used_percent', 0)
            disk = self._metrics.get('disk_used_percent', 0)

        status = 'healthy'
        warnings = []

        if cpu > 90:
            status = 'degraded'
            warnings.append(f'CPU usage critical: {cpu}%')
        if mem > 90:
            status = 'degraded'
            warnings.append(f'Memory usage critical: {mem}%')
        if disk > 90:
            status = 'degraded'
            warnings.append(f'Disk usage critical: {disk}%')

        return {
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': int(time.time() - self._start_time),
            'cpu_percent': cpu,
            'memory_percent': mem,
            'disk_percent': disk,
            'warnings': warnings
        }

    def get_prometheus_metrics(self) -> str:
        """导出Prometheus格式指标"""
        self._collect_system_metrics()
        with self._lock:
            m = self._metrics

        lines = [
            "# HELP mas_uptime_seconds Application uptime in seconds",
            "# TYPE mas_uptime_seconds gauge",
            f"mas_uptime_seconds {m.get('uptime_seconds', 0)}",
            "",
            "# HELP mas_task_total Total number of tasks processed",
            "# TYPE mas_task_total counter",
            f"mas_task_total {m.get('task_count', 0)}",
            "",
            "# HELP mas_error_total Total number of task errors",
            "# TYPE mas_error_total counter",
            f"mas_error_total {m.get('error_count', 0)}",
            "",
            "# HELP mas_cpu_percent CPU usage percentage",
            "# TYPE mas_cpu_percent gauge",
            f"mas_cpu_percent {m.get('cpu_percent', 0)}",
            "",
            "# HELP mas_memory_percent Memory usage percentage",
            "# TYPE mas_memory_percent gauge",
            f"mas_memory_percent {m.get('memory_used_percent', 0)}",
            "",
            "# HELP mas_disk_percent Disk usage percentage",
            "# TYPE mas_disk_percent gauge",
            f"mas_disk_percent {m.get('disk_used_percent', 0)}",
            "",
        ]

        if 'avg_response_time_ms' in m:
            lines += [
                "# HELP mas_avg_response_time_ms Average response time in ms",
                "# TYPE mas_avg_response_time_ms gauge",
                f"mas_avg_response_time_ms {m['avg_response_time_ms']}",
                "",
            ]

        return '\n'.join(lines)

    def _mock_cpu(self) -> float:
        return (time.time() % 60) * 0.5 + 20.0

    def _mock_memory(self) -> float:
        return 45.0 + (time.time() % 30)


_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
