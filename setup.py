import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

with open("servicecatalog_tools_helpers/requirements.txt", "r") as fh:
    requirements = fh.read().split("\n")

setuptools.setup(
    name="servicecatalog-tools-helpers",
    version="0.5.0",
    author="Eamonn Faherty",
    author_email="packages@designandsolve.co.uk",
    description="helpers for SCT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/eamonnfaherty/servicecatalog-tools-helpers",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': [
            'sct-tools-helpers = servicecatalog_tools_helpers.cli:cli'
        ]},
    install_requires=requirements,
)
