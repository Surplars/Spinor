// Abort the actual public VPU at each execution/held-completion phase.
#define main spike_driver_main
#include "gsim_spike_driver.cc"
#undef main
int main(int argc,char**argv){try{
  if(argc<2 || argc>3)throw std::runtime_error("Usage: flush-driver zero-image [mutate-rf]");
  Driver d;d.reset();std::ostringstream setup;
  setup<<std::hex<<0<<' '<<0x0100f1d7<<" 0 0 4 0 0 0 1 4 4 10 0 0 0 0 0 "<<argv[1]<<" -";
  std::istringstream config(setup.str());d.command(config);
  const auto original=d.architecture();
  std::array<uint64_t,64> seed{};
  for(unsigned k=0;k<64;k++){seed[k]=0xa59639ce17f082b4ULL^(0x123456789abcdefULL*k);d.context(k,true,seed[k]);}
  // Canonical encodings independently taken from upstream encoding.h.
  const std::array<uint32_t,16> raw={0x04000057,0x04004057,0x48042057,0x48052057,0x48062057,0x48072057,0x4806a057,0x4804a057,
    0x54000057,0x54004057,0x50003057,0x50000057,0x50004057,0xd4003057,0xd4000057,0xd4004057};
  unsigned aborted=0,held=0;bool mutation=false;
  for(auto base:raw)for(unsigned phase=0;phase<=220;phase++){
    auto instruction=base|(1u<<25)|(16u<<20)|(8u<<7);
    const auto format=base>>12&7;
    if(format==0)instruction|=24u<<15;
    else if(format==4)instruction|=1u<<15;
    else if(format==3)instruction|=31u<<15;
    d.dut.set_io$$core$$command$$bits$$instruction(instruction);
    d.dut.set_io$$core$$command$$bits$$scalar(33);d.dut.set_io$$core$$command$$bits$$scalar2(0);
    d.dut.set_io$$core$$command$$bits$$avl(0);d.dut.set_io$$core$$command$$bits$$token(aborted);
    d.dut.set_io$$core$$command$$valid(1);d.tick();d.check(d.dut.get_io$$core$$command$$ready(),"flush launch blocked");d.dut.set_io$$core$$command$$valid(0);
    bool saw=false;
    for(unsigned j=0;j<phase;j++){d.tick();d.check(d.architecture()==original,"publication before abort");saw|=d.dut.get_io$$core$$completion$$valid();}
    held+=saw;
    d.dut.set_io$$core$$flush(1);d.tick();d.check(!d.dut.get_io$$core$$completion$$valid(),"flush completion visible");d.dut.set_io$$core$$flush(0);
    for(unsigned j=0;j<20;j++){d.tick();d.check(!d.dut.get_io$$core$$completion$$valid(),"stale completion after abort");}
    d.check(d.architecture()==original,"flush CSR changed");
    if(argc==3 && !mutation){d.context(16,true,seed[16]^1);mutation=true;}
    for(unsigned k=0;k<64;k++)d.check(d.context(k,false,0)==seed[k],"flush committed RF changed");
    d.check(d.requests==0,"arithmetic emitted TL request");++aborted;
  }
  d.check(held>0,"held-completion coverage empty");
  std::cout<<"PASS public Zvbb flush aborted="<<aborted<<" held="<<held<<" RF_words_per_abort=64\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
