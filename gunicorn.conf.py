from models.database import init_db


def on_starting(server):
    init_db()

preload_app = True