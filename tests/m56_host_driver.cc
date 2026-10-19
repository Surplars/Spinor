// Adaptive public-port driver. All expected architectural values come from
// upstream Spike output files; no DUT result generates an expected result.
#include DUT_HEADER
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using Wide=unsigned _BitInt(128);
static constexpr uint64_t BASE=0x80010000;
struct Driver {
  DUT_CLASS dut;
  std::array<uint8_t,8192> ram{};
  uint64_t cycles=0,requests=0,responses=0,commands=0,reads=0;
  uint64_t fault_address=0,fault_length=0;
  bool pending=false,dvalid=false,denied=false;
  uint64_t address=0,data=0,reply_data=0;unsigned size=0,opcode=0,mask=0,waits=0;
  std::string negative;
  unsigned hostFrm=0,hostFlags=0;
  bool completionReady=false;
  void ready(bool value){completionReady=value;dut.set_io$$core$$completion$$ready(value);}
  void host(unsigned rm,unsigned flags){
    hostFrm=rm;hostFlags=flags;dut.set_io$$core$$fcsrHost$$frm(rm);dut.set_io$$core$$fcsrHost$$fflags(flags);
  }
  void check(bool ok,const std::string& message) {
    if(!ok)throw std::runtime_error(message+" command="+std::to_string(commands)+" cycle="+std::to_string(cycles));
  }
  uint64_t frm(){
#if ENABLE_FP
    return dut.get_io$$core$$frm();
#else
    return 0;
#endif
  }
  uint64_t flags(){
#if ENABLE_FP
    return dut.get_io$$core$$fflags();
#else
    return 0;
#endif
  }
  std::array<uint64_t,8> architecture(){return {dut.get_io$$core$$versions(),dut.get_io$$core$$vl(),dut.get_io$$core$$vtype(),dut.get_io$$core$$vstart(),dut.get_io$$core$$vxrm(),dut.get_io$$core$$vxsat(),frm(),flags()};}
  std::array<uint64_t,6> memory_status(){return {dut.get_io$$memoryStatus$$valid(),dut.get_io$$memoryStatus$$bits$$fault(),dut.get_io$$memoryStatus$$bits$$interrupted(),dut.get_io$$memoryStatus$$bits$$cause(),dut.get_io$$memoryStatus$$bits$$address(),dut.get_io$$memoryStatus$$bits$$element()};}
  void tick(bool resetting=false){
    const bool aready=!pending && !dvalid && cycles%3!=1;
    if(pending && !dvalid){
      if(waits)--waits;
      else {
        dvalid=true;reply_data=0;
        if(!denied){const auto beat=(address-BASE)&~uint64_t(7);for(unsigned j=0;j<8;j++)reply_data|=uint64_t(ram.at(beat+j))<<(8*j);}
        if(negative=="corrupt-load" && opcode==4 && !denied)reply_data^=1;
      }
    }
    dut.set_io$$tl$$a$$ready(aready);dut.set_io$$tl$$d$$valid(dvalid);
    dut.set_io$$tl$$d$$bits$$opcode(opcode==4?1:0);dut.set_io$$tl$$d$$bits$$size(size);
    dut.set_io$$tl$$d$$bits$$source(0);dut.set_io$$tl$$d$$bits$$param(0);dut.set_io$$tl$$d$$bits$$sink(0);
    dut.set_io$$tl$$d$$bits$$denied(denied);dut.set_io$$tl$$d$$bits$$corrupt(0);dut.set_io$$tl$$d$$bits$$data(reply_data);
    // GSIM outputs describe the pre-edge state; step also advances that edge.
    // Decide handshakes from these returned outputs and the inputs just set.
    dut.step();++cycles;
    const bool update=dut.get_io$$core$$fcsrHost$$flags$$valid();
    check(!update || (dut.get_io$$core$$completion$$valid() && !dut.get_io$$core$$completion$$bits$$illegal() && !dut.get_io$$memoryStatus$$valid()),"unowned flags sideband");
    if(update && (completionReady || negative=="early-merge"))
      host(hostFrm,hostFlags|unsigned(dut.get_io$$core$$fcsrHost$$flags$$bits()));
    check(cycles<50000000,"total timeout");
    if(resetting)return;
    if(dvalid && dut.get_io$$tl$$d$$ready()){
      if(opcode==0 && !denied){const auto beat=(address-BASE)&~uint64_t(7);for(unsigned j=0;j<8;j++)if(mask>>j&1)ram.at(beat+j)=data>>(8*j);}
      dvalid=false;pending=false;++responses;
    }
    if(dut.get_io$$tl$$a$$valid() && aready){
      check(!pending && !dvalid,"duplicate TL A");
      address=dut.get_io$$tl$$a$$bits$$address();size=dut.get_io$$tl$$a$$bits$$size();opcode=dut.get_io$$tl$$a$$bits$$opcode();
      mask=dut.get_io$$tl$$a$$bits$$mask();data=dut.get_io$$tl$$a$$bits$$data();
      check(size<=3 && (opcode==0 || opcode==4) && dut.get_io$$tl$$a$$bits$$source()==0 && dut.get_io$$tl$$a$$bits$$param()==0 && !dut.get_io$$tl$$a$$bits$$corrupt(),"invalid TL metadata");
      const auto bytes=uint64_t(1)<<size;
      check(!(address&(bytes-1)) && mask==(((uint64_t(1)<<bytes)-1)<<(address&7)),"invalid TL alignment/mask");
      check(address>=0x80000000 && address<0x90000000,"physical-window check emitted TL A");
      denied=address<BASE || address>BASE+ram.size()-bytes || (fault_length && address<fault_address+fault_length && fault_address<address+bytes);
      pending=true;waits=cycles%4;++requests;
    }
    check(!dut.get_io$$memoryStatus$$valid() || dut.get_io$$core$$completion$$valid(),"unowned memory status");
  }
  void reset(){
    host(0,0);
    dut.set_io$$core$$flush(0);dut.set_io$$core$$command$$valid(0);ready(0);
    dut.set_io$$core$$context$$valid(0);dut.set_io$$monitor$$a$$valid(0);dut.set_io$$monitor$$d$$ready(0);
    dut.set_reset(1);tick(true);tick(true);dut.set_reset(0);tick();
  }
  uint64_t context(unsigned index,bool write,uint64_t value){
    dut.set_io$$core$$context$$bits$$address(index);dut.set_io$$core$$context$$bits$$write(write);dut.set_io$$core$$context$$bits$$data(value);
    dut.set_io$$core$$context$$valid(1);tick();check(dut.get_io$$core$$context$$ready(),"context blocked");
    dut.set_io$$core$$context$$valid(0);tick();check(dut.get_io$$core$$contextResult$$valid(),"missing context result");
    if(!write)++reads;return dut.get_io$$core$$contextResult$$bits();
  }
  void command(std::istringstream& in){
    uint64_t id,raw,scalar,scalar2,avl,illegal,cause,tval,writes,result,vl,vtype,vstart,vxrm,vxsat,rounding,fflags;
    std::string rf_file,ram_file;unsigned delta,flagValid,mutate;
    check(bool(in>>std::hex>>id>>raw>>scalar>>scalar2>>avl>>illegal>>cause>>tval>>writes>>result>>vl>>vtype>>vstart>>vxrm>>vxsat>>rounding>>fflags>>rf_file>>ram_file>>delta>>flagValid>>mutate),"bad command fixture");
    check(id==commands && raw<=UINT32_MAX,"command sequence");
    const auto started=cycles,initial_requests=requests;const bool memory=(raw&127)==7 || (raw&127)==39;
    const Wide token=(Wide(0x52de)<<64)|(Wide(0xfedcab09)<<32)|id;
    const auto original=architecture();
    dut.set_io$$core$$command$$bits$$instruction(raw);dut.set_io$$core$$command$$bits$$scalar(scalar);dut.set_io$$core$$command$$bits$$scalar2(scalar2);
    dut.set_io$$core$$command$$bits$$avl(avl);dut.set_io$$core$$command$$bits$$token(token);dut.set_io$$core$$command$$valid(1);
    tick();check(dut.get_io$$core$$command$$ready(),"command blocked");dut.set_io$$core$$command$$valid(0);
    if(mutate)host(hostFrm<5?7:0,hostFlags^31);
    const auto beforeFlags=hostFlags;
    auto unpublished=[&](){
      const auto now=architecture();
      for(unsigned k=0;k<6;k++)if(!memory)check(now[k]==original[k],"early arithmetic publication");
      check(hostFlags==beforeFlags,"CPU FCSR changed before retirement");
      check(frm()==hostFrm && flags()==hostFlags,"host FCSR observation mismatch");
    };
    for(;;){
      tick();check(!dut.get_io$$core$$context$$ready() && !dut.get_io$$core$$command$$ready(),"owned command/context arbitration");if(!memory)unpublished();
      check(cycles-started<200000,"command timeout");if(dut.get_io$$core$$completion$$valid())break;
    }
    const auto held=architecture();const auto held_status=memory_status();const auto held_scalar=dut.get_io$$core$$completion$$bits$$scalar();
    auto completion=[&](){
      check(dut.get_io$$core$$completion$$valid(),"completion dropped");
      check(dut.get_io$$core$$fcsrHost$$flags$$valid()==flagValid,"flag delta ownership mismatch");
      check(dut.get_io$$core$$fcsrHost$$flags$$bits()==(delta^(negative=="wrong-delta" && flagValid?1:0)),"flag delta mismatch");
      check(dut.get_io$$core$$completion$$bits$$token()==(negative=="wrong-token"?token^(Wide(1)<<79):token),"completion token mismatch");
      check(dut.get_io$$core$$completion$$bits$$instruction()==raw && dut.get_io$$core$$completion$$bits$$illegal()==illegal && dut.get_io$$core$$completion$$bits$$writesScalar()==writes,"completion metadata mismatch");
      check(dut.get_io$$core$$completion$$bits$$scalar()==held_scalar && (!writes || held_scalar==result),"scalar result mismatch");
      check(dut.get_io$$memoryStatus$$valid()==memory,"memory status ownership");
      if(memory){
        const bool fault=cause && cause!=2;
        check(dut.get_io$$memoryStatus$$bits$$fault()==fault && !dut.get_io$$memoryStatus$$bits$$interrupted(),"memory fault mismatch");
        check(dut.get_io$$memoryStatus$$bits$$cause()==(fault?cause:0),"memory fault cause mismatch");
        check(dut.get_io$$memoryStatus$$bits$$address()==(fault?tval^(negative=="wrong-tval"?1:0):0),"memory fault address mismatch");
        check(dut.get_io$$memoryStatus$$bits$$element()==(fault?vstart:0),"memory fault element mismatch");
      }
    };
    completion();check(!pending && !dvalid,"completion before TL drain");if(cause==2)check(requests==initial_requests,"illegal command emitted TL traffic");
    for(unsigned k=0;k<id%4+1;k++){tick();unpublished();completion();check(architecture()==held && memory_status()==held_status,"unstable held completion");}
    ready(1);tick();completion();ready(0);tick();
    const std::array<uint64_t,7> expected={vl,vtype,vstart,vxrm,vxsat,rounding,fflags};const auto arch=architecture();
    for(unsigned k=0;k<7;k++)check(arch[k+1]==(expected[k]^(negative=="wrong-csr" && k==0?1:0)),"CSR mismatch index="+std::to_string(k));
    std::ifstream rf(rf_file);check(bool(rf),"RF fixture open");uint64_t word;
    for(unsigned k=0;k<64;k++){
      check(bool(rf>>std::hex>>word),"RF fixture short");if(negative=="wrong-rf" && k==16)word^=1;
      check(context(k,false,0)==word,"RF mismatch chunk="+std::to_string(k));
    }
    if(ram_file!="-"){
      std::ifstream image(ram_file);check(bool(image),"RAM fixture open");unsigned byte;
      for(unsigned k=0;k<ram.size();k++){check(bool(image>>std::hex>>byte) && byte<=255,"RAM fixture short");if(negative=="wrong-ram" && k==0)byte^=1;check(ram[k]==byte,"RAM mismatch byte="+std::to_string(k));}
    }
    check(!pending && !dvalid && requests==responses,"undrained TL bus");
    std::cout<<"CMD "<<id<<' '<<cycles-started<<' '<<requests-initial_requests<<'\n';++commands;
  }
  void run(const std::string& path){
    std::ifstream file;if(path!="-")file.open(path);
    auto&stream=path=="-"?std::cin:file;check(bool(stream),"stimulus open");reset();std::string line;
    while(std::getline(stream,line)){
      std::istringstream in(line);std::string kind;in>>kind;if(kind.empty() || kind[0]=='#')continue;
      if(kind=="P"){unsigned rm,flags;check(bool(in>>std::hex>>rm>>flags),"bad CPU FCSR fixture");host(rm,flags);tick();}
      else if(kind=="R"){
        unsigned reg;std::string bits;check(bool(in>>reg>>bits) && reg<32 && bits.size()==32,"bad RF fixture");
        context(2*reg,true,std::stoull(bits.substr(16),nullptr,16));context(2*reg+1,true,std::stoull(bits.substr(0,16),nullptr,16));
      }else if(kind=="M"){
        std::string bits;check(!pending && !dvalid && bool(in>>bits) && bits.size()==2*ram.size(),"bad RAM fixture");
        for(unsigned k=0;k<ram.size();k++)ram[k]=std::stoul(bits.substr(2*k,2),nullptr,16);
      }else if(kind=="F"){check(!pending && !dvalid && bool(in>>std::hex>>fault_address>>fault_length),"bad fault fixture");}
      else if(kind=="I")command(in);
      else throw std::runtime_error("unknown event");
    }
    std::cout<<"PASS host FCSR GSIM commands="<<commands<<" cycles="<<cycles<<" reads="<<reads<<" requests="<<requests<<" responses="<<responses<<'\n';
  }
};
int main(int argc,char**argv){try{if(argc<2 || argc>3)throw std::runtime_error("Usage: driver stimulus [negative-control]");Driver driver;if(argc==3)driver.negative=argv[2];driver.run(argv[1]);return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
