# First, specify the base Docker image.
# You can use any base image from Docker Hub or your own private registry.
FROM apify/actor-python:3.12

# Second, copy just requirements.txt into the Actor image,
# since it should be the only file that affects the dependency installation in the next step,
# in order to speed up the build process.
COPY requirements.txt ./

# Install the packages specified in requirements.txt,
# and make sure that the Playwright browsers are installed.
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium

# Next, copy the remaining files and directories with the source code.
# Since we do this after installing the dependencies, quick build will be possible if the source files change frequently.
COPY . ./

# Specify how to launch the source code of your Actor.
# By default, the "python3 -m src" command is run.
CMD ["python3", "-m", "src"]
