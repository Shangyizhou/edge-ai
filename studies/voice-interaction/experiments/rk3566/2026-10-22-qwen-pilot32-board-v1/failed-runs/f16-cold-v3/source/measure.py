"""Sample a declared process tree; keep platform memory quantities distinct."""

import os
import platform
from pathlib import Path
import threading
import time


class ResourceSampler:
    """CPU is process-tree CPU seconds / wall / logical host CPU count."""

    def __init__(self, pid=None, interval=0.2):
        import psutil

        self.psutil = psutil
        self.process = psutil.Process(pid or os.getpid())
        self.interval = interval
        self.samples = []
        self.stop_event = threading.Event()
        self.thread = None
        self.cpu_by_process = {}

    def sample(self):
        try:
            processes = [self.process] + self.process.children(recursive=True)
        except (self.psutil.NoSuchProcess, self.psutil.ZombieProcess):
            processes = []
        rss = 0.0
        pss = 0.0 if platform.system() == "Linux" else None
        for process in processes:
            try:
                times = process.cpu_times()
                identity = (process.pid, process.create_time())
                self.cpu_by_process[identity] = times.user + times.system
                memory = process.memory_info()
                rss += memory.rss
                if pss is not None:
                    pss += process.memory_full_info().pss
            except (self.psutil.NoSuchProcess, self.psutil.ZombieProcess):
                continue
        memory = self.psutil.virtual_memory()
        swap = self.psutil.swap_memory()
        sample = {
            "monotonic_seconds": time.perf_counter(),
            "cpu_seconds": sum(self.cpu_by_process.values()),
            "rss_bytes": int(rss),
            "pss_bytes": None if pss is None else int(pss),
            "host_mem_total_bytes": memory.total,
            "host_mem_available_bytes": memory.available,
            "host_swap_used_bytes": swap.used,
            "host_swap_in_bytes": swap.sin,
            "host_swap_out_bytes": swap.sout,
        }
        if platform.system() == "Linux":
            temperatures = {}
            for sensor in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
                try:
                    temperatures[sensor.parent.name] = float(sensor.read_text()) / 1000
                except (OSError, ValueError):
                    pass
            sample["thermal_zone_celsius"] = temperatures
        self.samples.append(sample)

    def start(self):
        self.sample()
        self.thread = threading.Thread(target=self._sample_loop, daemon=True)
        self.thread.start()
        return self

    def _sample_loop(self):
        while not self.stop_event.wait(self.interval):
            self.sample()

    def stop(self):
        self.stop_event.set()
        self.thread.join()
        self.sample()
        first, last = self.samples[0], self.samples[-1]
        wall = last["monotonic_seconds"] - first["monotonic_seconds"]
        cpu = max(0, last["cpu_seconds"] - first["cpu_seconds"])
        pss = [
            s["pss_bytes"] for s in self.samples if s["pss_bytes"] is not None
        ]
        return {
            "scope": "declared process and recursive children",
            "pid": self.process.pid,
            "sampling_interval_seconds": self.interval,
            "sample_count": len(self.samples),
            "wall_seconds": wall,
            "cpu_seconds": cpu,
            "host_logical_cpus": os.cpu_count(),
            "cpu_capacity_percent": cpu / wall / os.cpu_count() * 100,
            "peak_rss_bytes": max(s["rss_bytes"] for s in self.samples),
            "peak_pss_bytes": max(pss) if pss else None,
            "host_mem_total_bytes": first["host_mem_total_bytes"],
            "minimum_host_mem_available_bytes": min(
                s["host_mem_available_bytes"] for s in self.samples
            ),
            "host_swap_delta_bytes": last["host_swap_used_bytes"]
            - first["host_swap_used_bytes"],
            "host_swap_in_delta_bytes": last["host_swap_in_bytes"] - first["host_swap_in_bytes"],
            "host_swap_out_delta_bytes": last["host_swap_out_bytes"] - first["host_swap_out_bytes"],
            "swap_scope": "system-wide counters; not attributed to model process",
            "limitation": "sampled peak, not kernel high-water mark; "
            "last observed CPU of retired children is retained, so short "
            "child lifetimes can remain under-sampled; "
            "RSS and accelerator allocations may overlap",
        }
