import argparse
import os

from colab.app import build_demo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Identity Studio Gradio for Colab")
    parser.add_argument("--share", action="store_true", help="Enable public Gradio link")
    parser.add_argument("--port", type=int, default=7860, help="Port for Gradio")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server_name = "0.0.0.0"
    if os.environ.get("COLAB_RELEASE_TAG"):
        os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

    demo = build_demo()
    demo.queue().launch(
        share=args.share,
        server_name=server_name,
        server_port=args.port,
        show_error=True,
    )


if __name__ == "__main__":
    main()
