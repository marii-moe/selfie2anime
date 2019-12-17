FROM ugatit_ugatit:latest
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
#Has to be done to get notebook2script exporter working
RUN mv /home/fast/fastai_dev/dev/local /home/fast/fastai_dev/dev/fast
RUN . /home/fast/anaconda3/etc/profile.d/conda.sh && \
  conda activate fastai_dev && \
  conda develop /home/fast/fastai_dev/anime/local && \
  conda develop /home/fast/fastai_dev/dev/
CMD ["/home/fast/fastai_dev/startup.sh"]