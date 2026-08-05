# Repo-root passthroughs — the real targets live in apps/worker/Makefile, but
# "make verify-fleet" typed anywhere sensible should just work (client 2026-08-05:
# it was tried from the root and from apps/bff before the right directory).

verify-fleet:
	$(MAKE) -C apps/worker verify-fleet

rehearse:
	$(MAKE) -C apps/worker rehearse
