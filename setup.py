from setuptools import setup, find_packages

setup(
    name="tagesform",
    version="0.1",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'flask',
        'flask-sqlalchemy',
        'flask-login',
        'flask-migrate',
        'apscheduler',
        'pytest'
    ],
) 