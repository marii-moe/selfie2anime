#!/usr/bin/env bash
sudo docker build -t anime:latest .
sudo docker run --name anime -v ~/.fastai/:/home/fast/.fastai/ -v /home/molly/Projects/selfie2anime/anime:/home/fast/fastai_dev/anime -p 8888:8888/tcp --ipc=host --shm-size 8G --gpus all anime:latest
