
#include <cstring>
#include <iostream>
#include <stdio.h>
#include <stdlib.h>
#include <fstream>

#include <chrono>
#include <ctime>

#include <string>
#include <sstream>
#include <float.h>

#include <pyvnlb/cpp/utils/VnlbAsserts.h>
#include <pyvnlb/cpp/vnlb/VideoNLBayes.hpp>
#include <pyvnlb/cpp/pybind/video_io/interface.h>

extern "C" {
#include <pyvnlb/cpp/flow/tvl1flow_lib.h>
#include <pyvnlb/cpp/video_io/iio.h>
}


/*******************************

      Testing and CPP File IO 
      to verify exact
      numerical precision
      of Python API

*******************************/

void readVideoForVnlb(const ReadVideoParams& args) {

  // prints
  if (args.verbose){
    fprintf(stdout,"-- [readVideoForVnlb] Parameters --\n");
    fprintf(stdout,"video_paths: %s\n",args.video_paths);
    fprintf(stdout,"first_frame: %d\n",args.first_frame);
    fprintf(stdout,"last_frame: %d\n",args.last_frame);
    fprintf(stdout,"frame_step: %d\n",args.frame_step);
    fprintf(stdout,"(t,c,h,w): (%d,%d,%d,%d)\n",args.t,args.c,args.h,args.w);
  }
  
  // init videos 
  Video<float> cppVideo,pyVideo;
  cppVideo.loadVideo(args.video_paths,args.first_frame,args.last_frame,args.frame_step);
  float* cppPtr = cppVideo.data.data();
  int size = cppVideo.sz.whcf;
  std::memcpy(args.read_video,cppPtr,size*sizeof(float));

}