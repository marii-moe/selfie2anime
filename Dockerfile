FROM ugatit_ugatit:latest
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
#Has to be done to get notebook2script exporter working
RUN conda develop -n fastai2 ${FASTAI_DIR}/anime/selfie2anime && \
  conda run -n fastai2 pip install wandb
WORKDIR ${FASTAI_DIR}
#/jupyter-notebook
ENV PATH="/home/fast/anaconda3/bin/:${PATH}"
#CMD ["echo $PATH"]
#CMD ["find","/","-regex",".*jupyter-notebook"]
#CMD ["conda","run","-n","fastai2","whereis","jupyter"]
#CMD ["conda","run","-n","fastai2","jupyter","notebook","--ip=0.0.0.0"]
COPY ./startup.sh .
#CMD ["whereis","python"]
#CMD ["conda","run","-n","fastai2","python","-c","from fastai2 import *"]
CMD ["bash","/home/fast/fastai2/startup.sh"]
#CMD ["tail","-f", "/dev/null"]