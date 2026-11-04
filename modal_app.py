"""Deploy to Modal: `modal deploy modal_app.py` (reads META_API_KEY from your local .env)."""
import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir(".", "/root/app", ignore=[".git", ".env", "**/__pycache__", "fixtures/demo.recording"])
)
app = modal.App("safezone", image=image)


@app.function(secrets=[modal.Secret.from_dotenv()], min_containers=1)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    import sys

    sys.path.insert(0, "/root/app")
    from safezone.app import create_app

    return create_app()
