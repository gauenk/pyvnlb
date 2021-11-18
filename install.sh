#!/bin/bash

cmake -B build
make -C build -j swigvnlb
cd ./build/vnlb/python
python -m pip install . --user
cd ../../../
export OMP_NUM_THREADS=4
