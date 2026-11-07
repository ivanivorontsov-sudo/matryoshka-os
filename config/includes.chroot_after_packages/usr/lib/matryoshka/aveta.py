def estimate(files, total_bytes, bench_bytes, bench_sec, sample_files, sample_sec):
    files = max(0, int(files))
    total_bytes = max(0, int(total_bytes))
    per_byte = (bench_sec / bench_bytes) if bench_bytes and bench_sec and bench_sec > 0 else 0
    per_file = (sample_sec / sample_files) if sample_files and sample_sec and sample_sec > 0 else 0.02
    io = total_bytes * per_byte
    scan = files * per_file
    return max(1, int(io + scan + 0.5)) if files else 0

def refine(done_files, total_files, elapsed, initial):
    if done_files <= 0 or total_files <= 0:
        return initial
    rate = elapsed / done_files
    left = max(0, total_files - done_files) * rate
    return max(0, int(left + 0.5))
