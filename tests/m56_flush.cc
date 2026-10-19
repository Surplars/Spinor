// Abort the actual public VPU at each execution/held-completion phase.
#define main spike_driver_main
#include "m56_host_driver.cc"
#undef main
int main(int argc,char**argv){try{
  if(argc<3 || argc>4)throw std::runtime_error("Usage: host-flush zero-image ops [mutate-rf]");
  Driver d;d.reset();std::ostringstream setup;
  setup<<std::hex<<0<<' '<<0x0100f1d7<<" 0 0 4 0 0 0 1 4 4 10 0 0 0 0 0 "<<argv[1]<<" - 0 0 0";
  std::istringstream config(setup.str());d.command(config);
  d.host(3,16);d.tick();const auto original=d.architecture();
  std::array<uint64_t,64> seed{};
  for(unsigned k=0;k<64;k++){seed[k]=0xa59639ce17f082b4ULL^(0x123456789abcdefULL*k);d.context(k,true,seed[k]);}
  std::ifstream instructions(argv[2]);d.check(bool(instructions),"FP op fixture open");
  std::vector<uint32_t> raw;uint32_t opcode;while(instructions>>std::hex>>opcode)raw.push_back(opcode);
  d.check(raw.size()==8,"FP operation fixture size");
  seed[32]=seed[33]=0x7f8000017f800001ULL;seed[48]=seed[49]=0;
  d.context(32,true,seed[32]);d.context(33,true,seed[33]);d.context(48,true,seed[48]);d.context(49,true,seed[49]);
  unsigned aborted=0,held=0;bool mutation=false;
  for(auto base:raw)for(unsigned phase=0;phase<=220;phase++){
    auto instruction=base;
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
    if(argc==4 && !mutation){d.context(16,true,seed[16]^1);mutation=true;}
    for(unsigned k=0;k<64;k++)d.check(d.context(k,false,0)==seed[k],"flush committed RF changed");
    d.check(d.requests==0,"arithmetic emitted TL request");++aborted;
  }
  // The host monitor must identify the explicit ownership interface.
  d.dut.set_io$$monitor$$a$$bits$$opcode(4);d.dut.set_io$$monitor$$a$$bits$$param(0);
  d.dut.set_io$$monitor$$a$$bits$$size(3);d.dut.set_io$$monitor$$a$$bits$$source(3);
  d.dut.set_io$$monitor$$a$$bits$$address(16);d.dut.set_io$$monitor$$a$$bits$$mask(255);
  d.dut.set_io$$monitor$$a$$bits$$data(0);d.dut.set_io$$monitor$$a$$bits$$corrupt(0);
  d.dut.set_io$$monitor$$a$$valid(1);d.tick();d.check(d.dut.get_io$$monitor$$a$$ready(),"monitor blocked");
  d.dut.set_io$$monitor$$a$$valid(0);d.tick();
  for(unsigned i=0;i<4;i++){d.check(d.dut.get_io$$monitor$$d$$valid() && d.dut.get_io$$monitor$$d$$bits$$data()==0x5602,"host monitor identity");d.tick();}
  d.dut.set_io$$monitor$$d$$ready(1);d.tick();d.dut.set_io$$monitor$$d$$ready(0);d.tick();
  d.check(d.architecture()==original,"monitor changed state");
  d.check(held>0,"held-completion coverage empty");
  std::cout<<"PASS host FCSR FP flush aborted="<<aborted<<" held="<<held<<" RF_words_per_abort=64\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
