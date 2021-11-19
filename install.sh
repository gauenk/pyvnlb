#!/bin/bash

cmake -B build
make -C build -j swigpyvnlb
cd ./build/pyvnlb/python
python setup.py clean --all 
python -m pip install . --user
cd ../../../
export OMP_NUM_THREADS=4
echo "Be sure run \"export OMP_NUM_THREADS=4\" so this program executes more timely."
