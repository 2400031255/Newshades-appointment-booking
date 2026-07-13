from app import create_app, socketio

app = create_app()

# Required for flask-socketio with gevent worker
if __name__ == '__main__':
    socketio.run(app)
