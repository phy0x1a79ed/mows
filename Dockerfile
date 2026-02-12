ARG PKG_NAME=mows
ARG CONDA_ENV=${PKG_NAME}_env

FROM condaforge/mambaforge as build-env
# https://mamba.readthedocs.io/en/latest/user_guide/mamba.html

# Singularity uses tini, but raises warnings
# we set it up here correctly for singularity
ENV TINI_VERSION v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini

# scope var from global
ARG CONDA_ENV
COPY ./envs/base.yml /opt/env.yml
# Create conda environment:
# name must match what is in conda.yml
RUN mamba env create --no-default-packages -n $CONDA_ENV -f /opt/env.yml\
    && mamba clean -afy

# use a smaller runtime image
# jammy is ver. 22.04 LTS
# https://wiki.ubuntu.com/Releases
FROM ubuntu:jammy
# scope vars from global
ARG CONDA_ENV
ARG PKG_NAME
COPY --from=build-env /tini /tini
COPY --from=build-env /opt/conda/envs/${CONDA_ENV} /opt/conda/envs/${CONDA_ENV}
ENV PATH /opt/conda/envs/${CONDA_ENV}/bin:$PATH

# use the src code directly for instant changes!
COPY ./src/${PKG_NAME} /app/${PKG_NAME}_src
RUN echo "python -m ${PKG_NAME}_src \$@" >/app/${PKG_NAME} && chmod +x /app/${PKG_NAME}
ENV PATH /app:$PATH
ENV PYTHONPATH /app:$PYTHONPATH

## We do some umask munging to avoid having to use chmod later on,
## as it is painfully slow on large directores in Docker.
RUN old_umask=`umask` && \
    umask 0000 && \
    umask $old_umask
    
# singularity doesn't use the -s flag, and that causes warnings
RUN chmod +x /tini
ENTRYPOINT ["/tini", "-s", "--"]
