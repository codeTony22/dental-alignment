"""Research instruments — measurement tools that judge the pipeline's
output without being part of it. Nothing in here is imported by the
pipeline, the application layer, or any server; tests and operators are
the only consumers. (Deliberately NOT ``apps/worker/tools`` — that
directory is on the freeze line.)"""
