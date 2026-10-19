// Timing-only audit: keep control fields fixed, vary all nonexempt data.
#define main host_driver_main
#include "m56_host_driver.cc"
#undef main
#include <set>
struct Timing:Driver {
  struct Result{unsigned latency;bool illegal;};
  Result issue(uint32_t raw,uint64_t scalar=0,uint64_t avl=0){
    const auto begun=cycles;const Wide token=(Wide(0x56d1)<<64)|commands;
    dut.set_io$$core$$command$$bits$$instruction(raw);dut.set_io$$core$$command$$bits$$scalar(scalar);dut.set_io$$core$$command$$bits$$scalar2(0);dut.set_io$$core$$command$$bits$$avl(avl);dut.set_io$$core$$command$$bits$$token(token);
    dut.set_io$$core$$command$$valid(1);tick();check(dut.get_io$$core$$command$$ready(),"DIEL command blocked");dut.set_io$$core$$command$$valid(0);
    do{tick();check(cycles-begun<200000,"DIEL command timeout");}while(!dut.get_io$$core$$completion$$valid());
    check(dut.get_io$$core$$completion$$bits$$token()==token && dut.get_io$$core$$completion$$bits$$instruction()==raw,"DIEL completion identity");
    Result result{unsigned(cycles-begun),bool(dut.get_io$$core$$completion$$bits$$illegal())};
    ready(1);tick();ready(0);tick();++commands;return result;
  }
};
int main(int argc,char**argv){try{
  if(argc<2 || argc>3)throw std::runtime_error("Usage: DIEL opcode-catalog [corrupt-latency]");
  Timing d;d.reset();std::ifstream input(argv[1]);d.check(bool(input),"DIEL catalog open");
  std::string name;uint32_t base,mask;unsigned role;unsigned groups=0,legal=0,rejected=0,samples=0;uint64_t rng=0x56de12864ULL;
  while(input>>name>>std::hex>>base>>mask>>role){
    for(unsigned m:{0u,1u,2u,3u,5u,6u,7u})for(unsigned s=0;s<4;s++){
      if(m>=4 && s>m-5)continue;
      for(unsigned masking=0;masking<3;masking++){
        const unsigned typ=s<<3|m;auto configured=d.issue(typ<<20|1<<15|7<<12|3<<7|0x57,0,128);d.check(!configured.illegal,"DIEL config rejected");
        const auto fields=((masking==0)<<25)|(16u<<20)|(24u<<15)|(8u<<7);const auto raw=base|(fields&~mask);
        Timing::Result first{};
        for(unsigned pattern=0;pattern<4;pattern++){
          uint64_t scalar=pattern==0?0:pattern==1?~0ULL:pattern==2?0x8000000080000000ULL:0xa59639ce17f082b4ULL;
          for(unsigned r=0;r<32;r++)for(unsigned chunk=0;chunk<2;chunk++){
            rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;
            uint64_t value=pattern==0?0:pattern==1?~0ULL:pattern==2?0x8000000080000000ULL:rng;
            if(r==0)value=(role&4)?scalar:masking==2?0:0xa596a596a596a596ULL;
            if((role&1) && r>=24)value=0; // hold all gather-control group entries fixed
            d.context(2*r+chunk,true,value);
          }
          if(role&2)scalar=1; // scalar gather/slide amount is an exempt control
          auto result=d.issue(raw,scalar);++samples;
          if(argc==3 && pattern==1)++result.latency;
          if(!pattern)first=result;
          else d.check(first.latency==result.latency && first.illegal==result.illegal,"data-dependent completion latency "+name);
        }
        ++groups;if(first.illegal)++rejected;else ++legal;
        std::cout<<"DIEL "<<name<<' '<<(8<<s)<<' '<<m<<' '<<masking<<' '<<!first.illegal<<' '<<first.latency<<'\n';
      }
    }
  }
  d.check(samples && legal && d.requests==0,"empty or memory-dependent DIEL audit");
  std::cout<<"PASS DIEL sampled groups="<<groups<<" legal="<<legal<<" rejected="<<rejected<<" samples="<<samples<<" cycles="<<d.cycles<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
