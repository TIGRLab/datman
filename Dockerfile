FROM ubuntu:focal

# Install dependencies
RUN apt update && \
    apt install -y wget unzip git python3.8 python3-pip && \
    cd /usr/bin/ && \
    ln -s python3.8 python && \
    ln -s pip3 pip && \
    pip install --upgrade pip

# Install dcm2niix/v1.0.20210317
RUN cd /tmp && \
    wget https://github.com/rordenlab/dcm2niix/releases/download/v1.0.20210317/dcm2niix_lnx.zip && \
    unzip -d /usr/bin/ dcm2niix_lnx.zip

RUN cd / && git clone https://github.com/TIGRLab/datman.git && \
    cd datman && pip install .

ENV PATH="${PATH}:/datman/bin"
ENV DM_CONFIG=/config/main_config.yml
ENV DM_SYSTEM=docker

CMD ["/bin/bash"]
