def thread_count(args):
    args_threads = int(args.threads_per_proxy)
    if args.proxy:
        nproxies = int(len(args.proxy))
        return nproxies * args_threads
    else:
        return int(args_threads)
