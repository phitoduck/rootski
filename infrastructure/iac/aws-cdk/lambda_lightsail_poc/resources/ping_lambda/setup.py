from setuptools import find_packages, setup

setup(
    name="ping_lambda",
    package_dir={"": "."},
    packages=find_packages(),
    install_requires=["requests", "rich", "boto3"],
)
