// Public monitor version and disabled-FP policy, independent of Spike's FPU.
#define main spike_driver_main
#include "gsim_spike_driver.cc"
#undef main
#include <algorithm>
int main(int argc,char**argv){try{
  if(argc!=2)throw std::runtime_error("Need zero-RF fixture path");
  Driver h;h.reset();const auto arch=h.architecture();
  h.dut.set_io$$monitor$$a$$bits$$opcode(4);h.dut.set_io$$monitor$$a$$bits$$param(0);
  h.dut.set_io$$monitor$$a$$bits$$size(3);h.dut.set_io$$monitor$$a$$bits$$source(3);
  h.dut.set_io$$monitor$$a$$bits$$address(16);h.dut.set_io$$monitor$$a$$bits$$mask(255);
  h.dut.set_io$$monitor$$a$$bits$$data(0);h.dut.set_io$$monitor$$a$$bits$$corrupt(0);
  h.dut.set_io$$monitor$$a$$valid(1);h.tick();h.check(h.dut.get_io$$monitor$$a$$ready(),"monitor admission");
  h.dut.set_io$$monitor$$a$$valid(0);h.tick();
  for(unsigned i=0;i<4;i++){
    h.check(h.dut.get_io$$monitor$$d$$valid() && !h.dut.get_io$$monitor$$d$$bits$$denied(),"monitor reply");
    h.check(h.dut.get_io$$monitor$$d$$bits$$data()==0x5501 && h.dut.get_io$$monitor$$d$$bits$$source()==3 && h.dut.get_io$$monitor$$d$$bits$$size()==3,"M55 monitor identity");h.tick();
  }
  h.dut.set_io$$monitor$$d$$ready(1);h.tick();h.dut.set_io$$monitor$$d$$ready(0);h.tick();
  h.check(h.architecture()==arch,"monitor changed vector state");
  unsigned rejected=0;
#if !ENABLE_FP
  auto command=[&](uint32_t raw,uint64_t scalar,uint64_t avl,bool bad,uint64_t vl,uint64_t typ){
    std::ostringstream line;line<<std::hex<<h.commands<<' '<<raw<<' '<<scalar<<" 0 "<<avl<<' '<<bad<<' '<<(bad?2:0)<<" 0 "<<(!bad)<<' '<<(!bad?vl:0)<<' '<<vl<<' '<<typ<<" 0 0 0 0 0 "<<argv[1]<<" -";
    std::istringstream in(line.str());h.command(in);
  };
  for(unsigned m:{0u,1u,2u,6u,7u})for(unsigned length:{0u,128u}){
    const uint64_t typ=8|m,maximum=m<4?8u<<m:8u>>(8-m),vl=std::min(uint64_t(length),maximum);
    command(typ<<20|1<<15|7<<12|3<<7|0x57,0,length,false,vl,typ);
    for(unsigned rm=0;rm<8;rm++){
      command(3<<20|1<<15|1<<12|3<<7|0x73,rm<<5,0,true,vl,typ);++rejected;
      for(unsigned sub:{12u,20u,21u}){
        command(0x12<<26|1<<25|16<<20|sub<<15|1<<12|8<<7|0x57,0,0,true,vl,typ);++rejected;
      }
    }
  }
#endif
  std::cout<<"PASS M55 public monitor=0x5501 disabled_FP_rejections="<<rejected<<" commands="<<h.commands<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
