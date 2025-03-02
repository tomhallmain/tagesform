from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'], use_reloader=True, host='localhost', port=5000)
