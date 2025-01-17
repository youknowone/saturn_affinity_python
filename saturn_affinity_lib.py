# -*- coding: utf-8 -*-

import win32process
import win32api
import win32con
import win32gui

import cache_lib

processed_process = None
processed_time = 0
game_only_mode = False
game_set = set()

cpu_support_type = None
core_clusters = []
all_cluster_mask = 0

best_cluster_thread_count = 0

priority_updated_p_name = None


def get_number_of_processors():
    sysinfo = win32api.GetSystemInfo()
    return sysinfo[5]


def get_pname_from_window_hwnd(hwnd):
    try:
        pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = win32api.OpenProcess(win32con.MAXIMUM_ALLOWED, win32con.FALSE, pid[1])
        p_name = win32process.GetModuleFileNameEx(handle, 0)
        win32api.CloseHandle(handle)
        return pid, p_name
    except Exception as e:
        return None


def get_current_process():
    for retry in range(0, 3):
        try:
            hwnd = win32gui.GetForegroundWindow()
            process = get_pname_from_window_hwnd(hwnd)
            text = win32gui.GetWindowText(hwnd)
            return process[0], process[1], text
        except Exception as e:
            continue
    return None


def get_all_windows():
    def callback(hwnd, hwnds):
        if win32gui.IsWindowVisible(hwnd):
            try:
                process = get_pname_from_window_hwnd(hwnd)
                text = win32gui.GetWindowText(hwnd)
                if text:
                    hwnds.append((process[0], process[1], win32gui.GetWindowText(hwnd)))
            except Exception as e:
                pass
        return True

    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
    return hwnds


def update_process_affinity_and_priority(
    target_pname=None, cluster_mask=0, priority_level=win32process.NORMAL_PRIORITY_CLASS
):
    global priority_updated_p_name
    affinity_cluster_mask = 0
    for cluster_idx, cluster in enumerate(core_clusters):
        if cluster_mask & (1 << cluster_idx):
            affinity_cluster_mask += cluster["ClusterMask"]
    otherwise_cluster_mask = all_cluster_mask - affinity_cluster_mask
    # print("Best Cluster Mask: %s" % hex(best_cluster_mask))
    # print("Otherwise Cluster Mask: %s" % hex(otherwise_cluster_mask))

    enum_processes = win32process.EnumProcesses()
    for pid in enum_processes:
        try:
            handle = win32api.OpenProcess(win32con.MAXIMUM_ALLOWED, win32con.FALSE, pid)
            p_name = win32process.GetModuleFileNameEx(handle, 0)
            if handle:
                if target_pname is not None:
                    if p_name == target_pname:
                        if (
                            win32process.GetProcessAffinityMask(handle)[0]
                            != affinity_cluster_mask
                        ):
                            win32process.SetProcessAffinityMask(
                                handle, affinity_cluster_mask
                            )
                            print("Set affinity to best cluster for %s" % p_name)
                        if win32process.GetPriorityClass(handle) != priority_level:
                            win32process.SetPriorityClass(handle, priority_level)
                            print(
                                "Set priority to %s for %s" % (priority_level, p_name)
                            )
                            priority_updated_p_name = p_name
                    else:
                        if (
                            win32process.GetProcessAffinityMask(handle)[0]
                            != otherwise_cluster_mask
                        ):
                            win32process.SetProcessAffinityMask(
                                handle, otherwise_cluster_mask
                            )
                else:
                    if (
                        win32process.GetProcessAffinityMask(handle)[0]
                        != all_cluster_mask
                    ):
                        win32process.SetProcessAffinityMask(handle, all_cluster_mask)
                    if p_name == priority_updated_p_name:
                        win32process.SetPriorityClass(
                            handle, win32process.NORMAL_PRIORITY_CLASS
                        )
            win32api.CloseHandle(handle)
        except Exception as e:
            continue


def get_processor_structure():
    infos = cache_lib.GetLogicalProcessorInformation()
    cache_clusters = []

    smt_mask = 0
    non_smt_mask = 0

    for info in infos:
        if info.Relationship == 2:  # RelationCache
            if info.Cache.Level == 3:
                cache_clusters.append((info.ProcessorMask, info.Cache.Size))
        elif info.Relationship == 0:  # RelationProcessorCore
            if bin(info.ProcessorMask).count("1") > 1:
                smt_mask |= info.ProcessorMask
            else:
                non_smt_mask |= info.ProcessorMask

    cache_clusters = sorted(cache_clusters, key=lambda x: x[1], reverse=True)

    all_cluster_mask_local = 0

    core_clusters_local = []

    for cluster in cache_clusters:
        all_cluster_mask_local |= cluster[0]

    # Multi Cache Cluster CPU (Supported AMD CPU)
    if len(cache_clusters) > 1:
        support_type = "AMD_MultiCCX"
        for cluster in cache_clusters:
            core_clusters_local.append(
                {
                    "ClusterMask": cluster[0],
                    "ThreadCount": bin(cluster[0]).count("1"),
                    "CacheSize": cluster[1],
                }
            )
    elif smt_mask != all_cluster_mask_local:
        support_type = "Intel_BigLittle"
        core_clusters_local = [
            {
                "ClusterMask": smt_mask,
                "ThreadCount": bin(smt_mask).count("1"),
                "CacheSize": cache_clusters[0][1],
            },
            {
                "ClusterMask": non_smt_mask,
                "ThreadCount": bin(non_smt_mask).count("1"),
                "CacheSize": cache_clusters[0][1],
            },
        ]
    else:
        support_type = "Normal"
        core_clusters_local = [
            {
                "ClusterMask": smt_mask,
                "ThreadCount": bin(smt_mask).count("1"),
                "CacheSize": cache_clusters[0][1],
            },
        ]

    return core_clusters_local, all_cluster_mask_local, support_type


def get_cluster_count():
    return len(core_clusters)


# count of core in best cluster
def get_cluster_thread_count(cluster_index):
    return core_clusters[cluster_index]["ThreadCount"]


def get_cluster_cache_size(cluster_index, size_unit="MB"):
    cache_size = core_clusters[cluster_index]["CacheSize"]
    print(cache_size, core_clusters)
    if size_unit == "MB":
        return cache_size // 1048576
    elif size_unit == "KB":
        return cache_size // 1024
    else:
        return cache_size


# Check supported CPU types
def get_cpu_support_type():
    return cpu_support_type


core_clusters, all_cluster_mask, cpu_support_type = get_processor_structure()
