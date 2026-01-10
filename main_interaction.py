import os

from interaction_engine.injectors import InteractionInjector
from interaction_engine.config import TARGETS, LINK_DISCOVERY_LIMIT, LINK_SAMPLES_PER_PAGE


def main():
    debug = os.getenv("ICE_DEBUG", "0") == "1"
    samples_per_site = 1 if debug else 6
    enable_discovery = False if debug else True
    link_limit = 0 if debug else LINK_DISCOVERY_LIMIT
    link_samples = 0 if debug else LINK_SAMPLES_PER_PAGE

    injector = InteractionInjector(
        headless=True,
        max_wait=10 if debug else 15,
        use_js_interceptor=True,
        show_overlay_flag=True,
        debug_mode=debug,
    )
    try:
        injector.run_batch(
            TARGETS,
            samples_per_site=samples_per_site,
            enable_discovery=enable_discovery,
            link_limit=link_limit,
            link_samples=link_samples,
        )
    finally:
        injector.close()


if __name__ == "__main__":
    main()
