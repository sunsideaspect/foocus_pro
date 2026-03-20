import argparse
import os

from colab.app import OUTPUT_DIR, RUNTIME_HOME
from colab.app_ultimate import build_demo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch ULTIMATE Identity Studio Gradio for Colab")
    parser.add_argument("--share", action="store_true", help="Enable public Gradio link")
    parser.add_argument("--port", type=int, default=7860, help="Port for Gradio")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server_name = "0.0.0.0"
    if os.environ.get("COLAB_RELEASE_TAG"):
        os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

    demo = build_demo()
    launch_kwargs = {
        "share": args.share,
        "server_name": server_name,
        "server_port": args.port,
        "show_error": True,
    }
    allowed_paths = [str(RUNTIME_HOME), str(OUTPUT_DIR), "/tmp"]
    try:
        demo.queue().launch(**launch_kwargs, allowed_paths=allowed_paths)
    except TypeError:
        demo.queue().launch(**launch_kwargs)


if __name__ == "__main__":
    main()
