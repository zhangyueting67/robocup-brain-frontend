from setuptools import setup


setup(
    name="brain_frontend",
    version="0.1.0",
    packages=["brain_frontend"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/brain_frontend"]),
        ("share/brain_frontend", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="RoboCup Team",
    maintainer_email="maintainer@example.com",
    description="Speech interaction and high-level planning prototype",
    license="Apache-2.0",
    entry_points={"console_scripts": ["brain_node = brain_frontend.ros_node:main"]},
)
