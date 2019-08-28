FROM quay.io/pypa/manylinux2010_x86_64
COPY . /taf
RUN yum -y install swig pcsc-lite.x86_64 pcsc-lite-devel.x86_64 \
  pcsc-tools.x86_64 pcsc-lite-libs.x86_64 ykpers.x86_64
RUN find /usr/lib64 -type f | grep -i 'libykpers*\|libyubikey*' | xargs -i cp {} /taf/taf/libs/
RUN cd /taf && /opt/python/cp36-cp36m/bin/python setup.py sdist bdist_wheel clean --all
