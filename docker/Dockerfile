ARG ARENA_IMAGE=pebx-arena:dev
FROM ${ARENA_IMAGE}
USER root
WORKDIR /workspaces/physicalevobench_x
COPY pyproject.toml /workspaces/physicalevobench_x/
COPY src /workspaces/physicalevobench_x/src
RUN /isaac-sim/python.sh -m pip install --no-build-isolation -e .
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/isaac-sim/python.sh", "-m", "physicalevobench_x.cli"]
CMD ["--help"]
