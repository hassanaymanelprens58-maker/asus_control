import os
import sys
import time
import math
import multiprocessing
import tempfile
import ctypes

# ─────────────────────────────────────────────────────────────────────────────
# CPU Benchmark: prime-stress on every logical core (bypasses GIL via fork)
# ─────────────────────────────────────────────────────────────────────────────

def cpu_worker(duration, result_queue):
    """CPU Core Stress: tight prime-number loop across duration seconds."""
    count = 0
    start = time.time()
    while time.time() - start < duration:
        for n in range(2, 5000):
            is_prime = True
            for i in range(2, int(math.sqrt(n)) + 1):
                if n % i == 0:
                    is_prime = False
                    break
        count += 1
    result_queue.put(count)


def run_cpu_benchmark(duration=8):
    """Launches CPU stress workers on ALL logical cores using multiprocessing."""
    cores = multiprocessing.cpu_count() or 4
    result_queue = multiprocessing.Queue()
    processes = []

    for _ in range(cores):
        p = multiprocessing.Process(target=cpu_worker, args=(duration, result_queue))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    total_ops = 0
    while not result_queue.empty():
        total_ops += result_queue.get()

    score = round((total_ops / duration) * 100.0, 1)
    return score


# ─────────────────────────────────────────────────────────────────────────────
# Memory Benchmark: multi-channel parallel bandwidth via multiprocessing
# ─────────────────────────────────────────────────────────────────────────────

def _mem_worker(block_mb, iters, result_queue):
    """Single-process memory bandwidth worker (copy+write large block)."""
    size = block_mb * 1024 * 1024
    src = bytearray(os.urandom(size))
    dst = bytearray(size)
    t0 = time.time()
    for _ in range(iters):
        dst[:] = src
    elapsed = time.time() - t0
    gb = (block_mb * iters) / 1024.0
    result_queue.put(gb / elapsed if elapsed > 0 else 0.0)


def run_memory_benchmark(workers=4, block_mb=64, iters=8):
    """
    Fires 'workers' parallel processes each stressing a large memory block.
    Sum of bandwidths approximates the multi-channel DRAM throughput.
    """
    q = multiprocessing.Queue()
    procs = []
    for _ in range(workers):
        p = multiprocessing.Process(target=_mem_worker, args=(block_mb, iters, q))
        procs.append(p)
        p.start()
    for p in procs:
        p.join()

    total_bw = 0.0
    while not q.empty():
        total_bw += q.get()

    return round(total_bw, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Disk Benchmark: O_DIRECT-style sequential write + read via unbuffered I/O
# ─────────────────────────────────────────────────────────────────────────────

def run_disk_benchmark(file_size_mb=256, chunk_size_kb=512):
    """Measures sequential disk write and read bandwidth in MB/s."""
    temp_dir = tempfile.gettempdir()
    test_file = os.path.join(temp_dir, "asus_custom_bench.dat")
    chunk = b"X" * (chunk_size_kb * 1024)
    chunks_count = (file_size_mb * 1024) // chunk_size_kb

    # Write test
    start_write = time.time()
    try:
        with open(test_file, "wb", buffering=0) as f:
            for _ in range(chunks_count):
                f.write(chunk)
            os.fsync(f.fileno())
    except Exception as e:
        print(f"Disk write error: {e}")
        return 0.0, 0.0
    elapsed_write = time.time() - start_write
    write_speed = round(file_size_mb / elapsed_write, 2)

    # Read test (after write to ensure file is on disk)
    start_read = time.time()
    try:
        with open(test_file, "rb", buffering=0) as f:
            while f.read(chunk_size_kb * 1024):
                pass
    except Exception as e:
        print(f"Disk read error: {e}")
        return write_speed, 0.0
    elapsed_read = time.time() - start_read
    read_speed = round(file_size_mb / elapsed_read, 2)

    if os.path.exists(test_file):
        try:
            os.remove(test_file)
        except Exception:
            pass

    return write_speed, read_speed


# ─────────────────────────────────────────────────────────────────────────────
# GPU Emulated Benchmark: parallel floating-point vertex math (multi-process)
# ─────────────────────────────────────────────────────────────────────────────

def _gpu_worker(duration, result_queue):
    """Intensive trigonometric / matrix-like float math on a single core."""
    count = 0
    start = time.time()
    while time.time() - start < duration:
        for x in range(1, 2000):
            rad = math.radians(x)
            sin_x = math.sin(rad)
            cos_x = math.cos(rad)
            tan_x = math.tan(rad)
            _ = math.sqrt(abs(sin_x * cos_x + tan_x * sin_x - cos_x * tan_x + 0.001))
        count += 1
    result_queue.put(count)


def run_gpu_emulated_benchmark(duration=8):
    """
    Parallel floating-point shader-style math across ALL cores.
    Score is proportional to total iterations across all workers.
    """
    cores = multiprocessing.cpu_count() or 4
    q = multiprocessing.Queue()
    procs = []
    for _ in range(cores):
        p = multiprocessing.Process(target=_gpu_worker, args=(duration, q))
        procs.append(p)
        p.start()
    for p in procs:
        p.join()

    total = 0
    while not q.empty():
        total += q.get()

    return int((total / duration) * 10.0)


# ─────────────────────────────────────────────────────────────────────────────
# Standalone run
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Executing Custom Python Hardware Benchmark Suite...")
    print("------------------------------------------------")
    print("Testing CPU Compute...")
    cpu_score = run_cpu_benchmark(8)
    print(f"-> CPU Compute Score: {cpu_score} Ops/sec")

    print("Testing Memory Bandwidth (multi-channel)...")
    mem_score = run_memory_benchmark()
    print(f"-> Memory Bandwidth Score: {mem_score} GB/sec")

    print("Testing Disk sequential I/O...")
    disk_write, disk_read = run_disk_benchmark(256)
    print(f"-> Disk Speed: Write {disk_write} MB/s | Read {disk_read} MB/s")

    print("Testing 3D Vertex/GPU Math (parallel)...")
    gpu_score = run_gpu_emulated_benchmark(8)
    print(f"-> 3D Vertex Compute Score: {gpu_score} Points")
    print("------------------------------------------------")
    print("Hardware tests finished successfully!")
