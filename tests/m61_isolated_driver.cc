// Adaptive real-port execution of the registered top; no DUT trace replay.
#include DUT_HEADER
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
using Wide=unsigned _BitInt(128);
using Packet=std::array<uint64_t,15>;
static constexpr uint64_t BASE=0x80010000;
struct Driver {
  DUT_CLASS dut;
  std::array<uint8_t,8192> ram{};
  uint64_t cycles=0,commands=0,hardware=0,local=0,reads=0,requests=0,responses=0;
  uint64_t cpuFrm=0,cpuFlags=0;
  std::array<uint64_t,7> lastDoneState{};
  bool pending=false,dvalid=false,denied=false,blockA=false;
  uint64_t address=0,data=0,replyData=0,faultAddress=0,faultLength=0;
  unsigned size=0,opcode=0,mask=0,waits=0;
  std::string negative;
  void check(bool x,const std::string& message){if(!x)throw std::runtime_error(message+" cmd="+std::to_string(commands)+" cycle="+std::to_string(cycles));}
  void tick(bool resetting=false){
#if HOST_FCSR
    dut.set_io$$fcsrHost$$frm(cpuFrm);dut.set_io$$fcsrHost$$fflags(cpuFlags);
#endif
    bool ready=!blockA && !pending && !dvalid && cycles%3!=1;
    if(pending && !dvalid){if(waits)--waits;else{dvalid=true;replyData=0;if(!denied){auto beat=(address-BASE)&~uint64_t(7);for(unsigned j=0;j<8;j++)replyData|=uint64_t(ram.at(beat+j))<<(8*j);}}}
    dut.set_io$$tl$$a$$ready(ready);dut.set_io$$tl$$d$$valid(dvalid);
    dut.set_io$$tl$$d$$bits$$opcode(opcode==4?1:0);dut.set_io$$tl$$d$$bits$$param(0);
    dut.set_io$$tl$$d$$bits$$source(0);dut.set_io$$tl$$d$$bits$$size(size);dut.set_io$$tl$$d$$bits$$sink(0);
    dut.set_io$$tl$$d$$bits$$denied(denied);dut.set_io$$tl$$d$$bits$$corrupt(0);dut.set_io$$tl$$d$$bits$$data(replyData);
    dut.step();++cycles;check(cycles<80000000,"timeout");if(resetting)return;
    if(dvalid && dut.get_io$$tl$$d$$ready()){
      if(opcode!=4 && !denied){auto beat=(address-BASE)&~uint64_t(7);for(unsigned j=0;j<8;j++)if(mask>>j&1)ram.at(beat+j)=data>>(8*j);}
      pending=false;dvalid=false;++responses;
    }
    if(ready && dut.get_io$$tl$$a$$valid()){
      check(!pending,"duplicate TL A");address=dut.get_io$$tl$$a$$bits$$address();data=dut.get_io$$tl$$a$$bits$$data();
      size=dut.get_io$$tl$$a$$bits$$size();opcode=dut.get_io$$tl$$a$$bits$$opcode();mask=dut.get_io$$tl$$a$$bits$$mask();
      check(size<=3 && (opcode==0 || opcode==4) && dut.get_io$$tl$$a$$bits$$source()==0 && dut.get_io$$tl$$a$$bits$$param()==0 && !dut.get_io$$tl$$a$$bits$$corrupt(),"TL metadata");
      auto bytes=uint64_t(1)<<size;check(!(address&(bytes-1)) && mask==(((uint64_t(1)<<bytes)-1)<<(address&7)),"TL alignment/lane");
      denied=address<BASE || address>BASE+ram.size()-bytes || (faultLength && address<faultAddress+faultLength && faultAddress<address+bytes);
      pending=true;waits=3+cycles%5;++requests;
    }
  }
  void reset(){
    dut.set_io$$offer$$valid(0);dut.set_io$$grant$$valid(0);dut.set_io$$done$$ready(0);dut.set_io$$stop(0);
    dut.set_io$$contextMode(0);dut.set_io$$context$$valid(0);dut.set_io$$contextResult$$ready(0);
    dut.set_io$$monitor$$a$$valid(0);dut.set_io$$monitor$$d$$ready(0);
    dut.set_reset(1);tick(true);tick(true);dut.set_reset(0);tick();tick();tick();
  }
  std::array<uint64_t,7> status(){return {dut.get_io$$status$$bits$$vl(),dut.get_io$$status$$bits$$vtype(),dut.get_io$$status$$bits$$vstart(),dut.get_io$$status$$bits$$vxrm(),dut.get_io$$status$$bits$$vxsat(),dut.get_io$$status$$bits$$frm(),dut.get_io$$status$$bits$$fflags()};}
  std::array<uint64_t,7> doneState(){return {dut.get_io$$done$$bits$$state$$vl(),dut.get_io$$done$$bits$$state$$vtype(),dut.get_io$$done$$bits$$state$$vstart(),dut.get_io$$done$$bits$$state$$vxrm(),dut.get_io$$done$$bits$$state$$vxsat(),dut.get_io$$done$$bits$$state$$frm(),dut.get_io$$done$$bits$$state$$fflags()};}
  Packet preview(){
    Wide t=dut.get_io$$preview$$bits$$reply$$completion$$token();
    return {uint64_t(t),uint64_t(t>>64),dut.get_io$$preview$$bits$$reply$$completion$$scalar(),dut.get_io$$preview$$bits$$reply$$completion$$writesScalar(),dut.get_io$$preview$$bits$$reply$$completion$$illegal(),dut.get_io$$preview$$bits$$reply$$completion$$instruction(),dut.get_io$$preview$$bits$$reply$$memory(),dut.get_io$$preview$$bits$$reply$$stopped(),dut.get_io$$preview$$bits$$reply$$exception(),dut.get_io$$preview$$bits$$reply$$cause(),dut.get_io$$preview$$bits$$reply$$tval(),dut.get_io$$preview$$bits$$reply$$rawMemoryCause(),dut.get_io$$preview$$bits$$reply$$element(),dut.get_io$$preview$$bits$$flagsValid(),dut.get_io$$preview$$bits$$flags()};
  }
  Packet done(){
    Wide t=dut.get_io$$done$$bits$$result$$reply$$completion$$token();
    return {uint64_t(t),uint64_t(t>>64),dut.get_io$$done$$bits$$result$$reply$$completion$$scalar(),dut.get_io$$done$$bits$$result$$reply$$completion$$writesScalar(),dut.get_io$$done$$bits$$result$$reply$$completion$$illegal(),dut.get_io$$done$$bits$$result$$reply$$completion$$instruction(),dut.get_io$$done$$bits$$result$$reply$$memory(),dut.get_io$$done$$bits$$result$$reply$$stopped(),dut.get_io$$done$$bits$$result$$reply$$exception(),dut.get_io$$done$$bits$$result$$reply$$cause(),dut.get_io$$done$$bits$$result$$reply$$tval(),dut.get_io$$done$$bits$$result$$reply$$rawMemoryCause(),dut.get_io$$done$$bits$$result$$reply$$element(),dut.get_io$$done$$bits$$result$$flagsValid(),dut.get_io$$done$$bits$$result$$flags()};
  }
  uint64_t context(unsigned index,bool write,uint64_t value){
    dut.set_io$$contextMode(1);dut.set_io$$context$$bits$$address(index);dut.set_io$$context$$bits$$write(write);dut.set_io$$context$$bits$$data(value);
    dut.set_io$$context$$valid(1);unsigned timeout=0;do{tick();check(++timeout<50,"context admission");}while(!dut.get_io$$context$$ready());
    dut.set_io$$context$$valid(0);timeout=0;do{tick();check(++timeout<50,"context response");}while(!dut.get_io$$contextResult$$valid());
    uint64_t result=dut.get_io$$contextResult$$bits();
    for(unsigned j=0;j<2;j++){tick();check(dut.get_io$$contextResult$$valid() && dut.get_io$$contextResult$$bits()==result && !dut.get_io$$offer$$ready(),"context hold");}
    dut.set_io$$contextResult$$ready(1);tick();check(dut.get_io$$contextResult$$valid(),"context consumed twice");dut.set_io$$contextResult$$ready(0);
    if(!write)++reads;return result;
  }
  uint64_t monitor(unsigned offset){
    dut.set_io$$monitor$$a$$bits$$opcode(4);dut.set_io$$monitor$$a$$bits$$param(0);dut.set_io$$monitor$$a$$bits$$size(3);dut.set_io$$monitor$$a$$bits$$source(3);
    dut.set_io$$monitor$$a$$bits$$address(offset);dut.set_io$$monitor$$a$$bits$$mask(255);dut.set_io$$monitor$$a$$bits$$data(0);dut.set_io$$monitor$$a$$bits$$corrupt(0);
    dut.set_io$$monitor$$a$$valid(1);unsigned timeout=0;do{tick();check(++timeout<50,"monitor A");}while(!dut.get_io$$monitor$$a$$ready());dut.set_io$$monitor$$a$$valid(0);
    timeout=0;do{tick();check(++timeout<50,"monitor D");}while(!dut.get_io$$monitor$$d$$valid());
    uint64_t value=dut.get_io$$monitor$$d$$bits$$data();
    for(unsigned j=0;j<3;j++){tick();check(dut.get_io$$monitor$$d$$valid() && dut.get_io$$monitor$$d$$bits$$data()==value && dut.get_io$$monitor$$d$$bits$$source()==3 && !dut.get_io$$monitor$$d$$bits$$denied(),"monitor hold");}
    dut.set_io$$monitor$$d$$ready(1);tick();dut.set_io$$monitor$$d$$ready(0);return value;
  }
  void monitorBurst(){
    const uint64_t offsets[3]={0,0x20,0x10};
    const uint64_t values[3]={0x4c495348,(uint64_t(1)<<48)|(uint64_t(32)<<32)|(64<<16)|128,HOST_FCSR?0x5602u:0x5501u};
    unsigned sent=0,received=0,timeout=0;
    dut.set_io$$monitor$$d$$ready(0);dut.set_io$$monitor$$a$$valid(1);
    while(sent<3){
      dut.set_io$$monitor$$a$$bits$$address(offsets[sent]);dut.set_io$$monitor$$a$$bits$$source(sent+1);
      tick();check(++timeout<80,"monitor burst acceptance");if(dut.get_io$$monitor$$a$$ready())++sent;
    }
    dut.set_io$$monitor$$a$$valid(0);
    for(unsigned j=0;j<5;j++){tick();check(dut.get_io$$monitor$$d$$valid() && dut.get_io$$monitor$$d$$bits$$data()==values[0],"monitor burst response hold");}
    dut.set_io$$monitor$$d$$ready(1);timeout=0;
    while(received<3){tick();check(++timeout<80,"monitor burst response drain");if(dut.get_io$$monitor$$d$$valid()){
      check(dut.get_io$$monitor$$d$$bits$$source()==received+1 && dut.get_io$$monitor$$d$$bits$$data()==values[received] && !dut.get_io$$monitor$$d$$bits$$denied(),"monitor burst order/source/data");++received;
    }}
    dut.set_io$$monitor$$d$$ready(0);tick();tick();
  }
  void monitorControl(uint64_t value,unsigned width,bool denied){
    dut.set_io$$monitor$$a$$bits$$opcode(0);dut.set_io$$monitor$$a$$bits$$param(0);dut.set_io$$monitor$$a$$bits$$size(width);
    dut.set_io$$monitor$$a$$bits$$source(2);dut.set_io$$monitor$$a$$bits$$address(0x40);dut.set_io$$monitor$$a$$bits$$mask(width==2?15:255);
    dut.set_io$$monitor$$a$$bits$$data(value);dut.set_io$$monitor$$a$$bits$$corrupt(0);dut.set_io$$monitor$$a$$valid(1);
    unsigned timeout=0;do{tick();check(++timeout<80,"monitor control A");}while(!dut.get_io$$monitor$$a$$ready());dut.set_io$$monitor$$a$$valid(0);
    timeout=0;do{tick();check(++timeout<80,"monitor control D");}while(!dut.get_io$$monitor$$d$$valid());
    check(dut.get_io$$monitor$$d$$bits$$denied()==denied && dut.get_io$$monitor$$d$$bits$$source()==2 && dut.get_io$$monitor$$d$$bits$$opcode()==0,"monitor control denial/ack");
    dut.set_io$$monitor$$d$$ready(1);tick();dut.set_io$$monitor$$d$$ready(0);tick();
  }
  void begin(uint32_t raw,uint64_t scalar,uint64_t scalar2,uint64_t avl,Wide token){
    dut.set_io$$contextMode(0);dut.set_io$$offer$$bits$$instruction(raw);dut.set_io$$offer$$bits$$scalar(scalar);dut.set_io$$offer$$bits$$scalar2(scalar2);dut.set_io$$offer$$bits$$avl(avl);dut.set_io$$offer$$bits$$token(token);
    dut.set_io$$offer$$valid(1);unsigned timeout=0;do{tick();check(++timeout<50,"offer admission");}while(!dut.get_io$$offer$$ready());dut.set_io$$offer$$valid(0);++hardware;
  }
  Packet waitPreview(){unsigned timeout=0;do{tick();check(!dut.get_io$$protocolError(),"protocol error before grant");check(++timeout<200000,"preview timeout");}while(!dut.get_io$$preview$$valid());return preview();}
  Packet authorize(Wide token,bool stopTogether=false){
    auto initial=status();
    if(negative=="wrong-grant")token^=Wide(1)<<79;
    dut.set_io$$stop(stopTogether);dut.set_io$$grant$$bits(token);dut.set_io$$grant$$valid(1);tick();check(dut.get_io$$grant$$ready(),"grant not accepted");dut.set_io$$grant$$valid(0);
    if(negative=="wrong-grant"){
      for(unsigned i=0;i<12;i++)tick();check(dut.get_io$$protocolError() && !dut.get_io$$done$$valid() && !dut.get_io$$offer$$ready(),"wrong grant not fail closed");
      auto current=status();for(unsigned i=0;i<5;i++)check(current[i]==initial[i],"wrong grant published state");throw std::runtime_error("EXPECTED wrong grant rejected without publication");
    }
    unsigned timeout=0;do{tick();check(!dut.get_io$$protocolError(),"protocol error after grant");check(++timeout<50,"done timeout");}while(!dut.get_io$$done$$valid());
    Packet result=done();lastDoneState=doneState();check(lastDoneState==status(),"done publication snapshot");
#if HOST_FCSR
    check(lastDoneState[5]==cpuFrm && lastDoneState[6]==cpuFlags,"host FCSR observation at done");
#endif
    for(unsigned i=0;i<4;i++){tick();check(dut.get_io$$done$$valid() && done()==result && doneState()==lastDoneState && !dut.get_io$$offer$$ready() && !dut.get_io$$context$$ready(),"done hold/owner/state");}
    dut.set_io$$done$$ready(1);tick();check(dut.get_io$$done$$valid(),"lost done");dut.set_io$$done$$ready(0);dut.set_io$$stop(0);
#if HOST_FCSR
    if(result[13])cpuFlags|=result[14];
#endif
    tick();tick();tick();return result;
  }
  void command(const std::string& line,const std::array<uint64_t,64>& expected){
    bool localOperation=false;
    std::istringstream in(line);uint64_t id,raw,scalar,scalar2,avl,illegal,cause,tval,writes,value,vl,type,start,rm,sat,frm,flags;
    check(bool(in>>std::hex>>id>>raw>>scalar>>scalar2>>avl>>illegal>>cause>>tval>>writes>>value>>vl>>type>>start>>rm>>sat>>frm>>flags),"fixture syntax");
    std::string marker,ramFile;in>>marker>>ramFile;
    check(id==commands,"fixture id");
#if HOST_FCSR
    if((raw&127)==0x73 && raw>>20==3){
      check(value==(cpuFrm<<5|cpuFlags),"host FCSR old value");cpuFrm=scalar>>5&7;cpuFlags=scalar&31;tick();tick();tick();++local;localOperation=true;
    }else
#endif
    {
      auto initial=status();Wide token=(Wide(0xcafe)<<64)|id;begin(raw,scalar,scalar2,avl,token);Packet p=waitPreview();
      for(unsigned i=0;i<5;i++){tick();check(dut.get_io$$preview$$valid() && preview()==p && !dut.get_io$$offer$$ready() && !dut.get_io$$context$$ready(),"preview hold/owner");auto s=status();if(!p[6]){for(unsigned k=0;k<5;k++)check(s[k]==initial[k],"early architecture publication");}}
      check(p[0]==uint64_t(token) && p[1]==uint64_t(token>>64) && p[5]==raw,"result identity");
      check(p[4]==illegal && p[3]==writes && (!writes || p[2]==value) && p[9]==cause && p[10]==(illegal?raw:tval) && !p[7],"preview result mismatch");
      if(commands%71==0){check(monitor(0)==0x4c495348,"monitor magic");check(preview()==p && dut.get_io$$preview$$valid(),"monitor disturbed preview");}
      Packet ack=authorize(token);check(ack==p,"preview/done mismatch");
    }
    auto state=status();std::array<uint64_t,7> target={vl,type,start,rm,sat,frm,flags};
    for(unsigned i=0;i<7;i++){
#if !ENABLE_FP
      if(i>=5)continue;
#endif
      check(state[i]==(target[i]^(negative=="wrong-csr" && i==0?1:0)),"CSR mismatch");
      if(!localOperation && !(HOST_FCSR && i==6))check(lastDoneState[i]==target[i],"done CSR reference mismatch");
    }
    for(unsigned r=0;r<64;r++){uint64_t got=context(r,false,0);check(got==(expected[r]^(negative=="wrong-rf" && r==0?1:0)),"RF mismatch");}
    if(!ramFile.empty() && ramFile!="-"){
      check(marker=="@","RAM marker");std::ifstream image(ramFile);unsigned byte;
      check(bool(image),"RAM reference open");for(unsigned i=0;i<ram.size();i++){check(bool(image>>std::hex>>byte) && byte<=255,"RAM reference short");check(ram[i]==byte,"RAM mismatch");}
    }
    check(requests==responses && !pending && !dvalid,"command bus drain");
    ++commands;
  }
  Packet operation(uint32_t raw,uint64_t scalar=0,uint64_t scalar2=0,uint64_t avl=0,bool stopTogether=false){
    Wide token=(Wide(0x61aa)<<64)|hardware;begin(raw,scalar,scalar2,avl,token);Packet p=waitPreview();
    check(p[0]==uint64_t(token) && p[1]==uint64_t(token>>64),"directed identity");
    Packet ack=authorize(token,stopTogether);check(p==ack,"directed preview/done");++commands;return ack;
  }
  void config(unsigned sew,unsigned length){
    unsigned s=sew==8?0:sew==16?1:sew==32?2:3;
    Packet p=operation((s<<3)<<20|1<<15|7<<12|3<<7|0x57,0,0,length);
    check(!p[4] && p[3] && p[2]==length && status()[0]==length,"directed vset");
  }
  void canceled(Wide token){
    unsigned timeout=0;do{tick();check(!dut.get_io$$done$$valid() && !dut.get_io$$protocolError(),"cancel returned done/error");check(++timeout<40,"cancel timeout");}while(!dut.get_io$$canceled$$valid());
    check(dut.get_io$$canceled$$bits()==token,"cancel identity");dut.set_io$$stop(0);tick();tick();tick();
  }
  void directed(){
#if HOST_FCSR
    // Observations follow the committed host FCSR even before the first
    // offer, and during a context transaction with no execution snapshot.
    cpuFrm=3;cpuFlags=5;tick();tick();tick();context(0,false,0);
    check(status()[5]==3 && status()[6]==5,"host FCSR context observation");
    cpuFrm=cpuFlags=0;tick();tick();tick();
#endif
    check(monitor(0)==0x4c495348,"monitor magic");
    check(monitor(0x10)==(HOST_FCSR?0x5602:0x5501),"monitor configuration ID");
    monitorBurst();
    auto sequence=monitor(0x48);monitorControl(1,3,false);check(monitor(0x48)==sequence+1,"snapshot control");
    monitorControl((uint64_t(1)<<40)|1,3,true);check(monitor(0x48)==sequence+1,"invalid 64-bit control had effect");
    monitorControl(0xffffffff00000001ull,2,false);check(monitor(0x48)==sequence+2,"ignored upper 32 data bits");
    monitorControl(4,2,true);monitorControl(3,3,true);monitorControl(2,3,false);
    check(monitor(0x48)==sequence+2 && !(monitor(0x38)&16),"monitor clear semantics");
    config(8,4);
    for(unsigned stage=0;stage<2;stage++){
      if(!stage)dut.set_io$$stop(1); // raw stop coincident with outer offer.fire
      Wide token=(Wide(0xce61)<<64)|stage;begin(1<<15|7<<12|3<<7|0x57,0,0,2,token);
      if(stage)waitPreview();dut.set_io$$stop(1);canceled(token);
      check(status()[0]==4,"canceled VSET published VL");
    }
    Wide token=(Wide(0x6161)<<64)|0x55;begin(1<<15|7<<12|3<<7|0x57,0,0,3,token);Packet p=waitPreview();
    check(status()[0]==4,"preview already published");check(authorize(token,true)==p && status()[0]==3,"grant must win coincident stop");++commands;
    for(unsigned i=0;i<64;i++)context(i,true,0);
    for(unsigned i=0;i<ram.size();i++)ram[i]=(i*17+3)&255;
    config(8,4);p=operation(0x02040407,BASE);
    check(p[6] && !p[7] && !p[8] && requests==4 && responses==4,"registered load sequence");
    uint64_t word=0;for(unsigned i=0;i<4;i++)word|=uint64_t(ram[i])<<(8*i);
    check(context(16,false,0)==word,"registered load RF");
    p=operation(0x02040427,BASE+64);
    for(unsigned i=0;i<4;i++)check(ram[64+i]==ram[i],"registered store data");
    check(!p[8] && !pending && requests==responses,"store bus drain");
    faultAddress=BASE+128;faultLength=1;p=operation(0x02040407,BASE+128);
    check(p[6] && p[8] && !p[7] && p[9]==5 && p[10]==BASE+128,"denied fault ownership");faultLength=0;
    // A has entered the registered slice but the fabric has not accepted it.
    // Stop must retain that published request and eventually consume its D.
    for(unsigned i=0;i<64;i++)context(i,true,0);
    config(8,4);blockA=true;uint64_t before=requests;token=(Wide(0x6162)<<64)|0x66;
    begin(0x02040407,BASE,0,0,token);unsigned timeout=0;
    do{tick();check(++timeout<1000,"stalled A timeout");}while(!dut.get_io$$tl$$a$$valid());
    auto heldAddress=dut.get_io$$tl$$a$$bits$$address();auto heldSize=dut.get_io$$tl$$a$$bits$$size();auto heldMask=dut.get_io$$tl$$a$$bits$$mask();
    dut.set_io$$stop(1);
    for(unsigned i=0;i<7;i++){tick();check(dut.get_io$$tl$$a$$valid() && dut.get_io$$tl$$a$$bits$$address()==heldAddress && dut.get_io$$tl$$a$$bits$$size()==heldSize && dut.get_io$$tl$$a$$bits$$mask()==heldMask && !dut.get_io$$canceled$$valid() && !dut.get_io$$done$$valid(),"stop withdrew held A");}
    check(monitor(0)==0x4c495348,"monitor during stopped memory");blockA=false;p=waitPreview();
    check(p[6] && p[7] && !p[8] && requests==before+1 && responses==requests,"memory stop/response drain");
    check(authorize(token)==p && status()[2]==0,"stopped pending load must restart the uncommitted element");
    check(context(16,false,0)==0,"stopped pending load must not publish response data");++commands;
    // Retry from architectural vstart, with the original unmodified base.
    p=operation(0x02040407,BASE);check(!p[7] && !p[8] && status()[2]==0,"memory restart completion");
    check(context(16,false,0)==word,"memory restart RF");
    config(8,4);blockA=true;before=requests;token=(Wide(0x6163)<<64)|0x67;
    begin(0x02040427,BASE+513,0,0,token);timeout=0;
    do{tick();check(++timeout<1000,"stalled store A timeout");}while(!dut.get_io$$tl$$a$$valid());
    auto heldData=dut.get_io$$tl$$a$$bits$$data();heldAddress=dut.get_io$$tl$$a$$bits$$address();
    dut.set_io$$stop(1);
    for(unsigned i=0;i<7;i++){tick();check(dut.get_io$$tl$$a$$valid() && dut.get_io$$tl$$a$$bits$$address()==heldAddress && dut.get_io$$tl$$a$$bits$$data()==heldData && !dut.get_io$$canceled$$valid(),"stop withdrew held store");}
    blockA=false;p=waitPreview();check(p[7] && !p[8] && requests==before+1 && responses==requests,"store stop drain");
    check(authorize(token)==p && status()[2]==1 && ram[513]==ram[0] && ram[514]==uint8_t(514*17+3),"irrevocable store prefix");++commands;
    p=operation(0x02040427,BASE+513);check(!p[7] && status()[2]==0,"store prefix retry");
    for(unsigned i=0;i<4;i++)check(ram[513+i]==ram[i],"store retry original base");
#if ENABLE_FP
    config(32,1);
#if HOST_FCSR
    cpuFrm=3;cpuFlags=0;tick();tick();tick();
#else
    operation(0x003091f3,3<<5);
#endif
    context(32,true,0x3f800000);context(48,true,0x33800000);
    token=(Wide(0xf161)<<64)|0x77;begin(0x030c1457,0,0,0,token);
#if HOST_FCSR
    // Perturbation checks the snapshot, not permission for real younger CSR
    // writes to pass an irrevocable older vector instruction in the CPU.
    cpuFrm=2;
#endif
    p=waitPreview();check(!p[4],"FP rejected");
#if HOST_FCSR
    check(p[13] && p[14]==1 && cpuFlags==0,"FP delta/early flags");
#endif
    check(authorize(token)==p,"FP grant/done");
    check((context(16,false,0)&0xffffffff)==0x3f800001,"outer-offer frm snapshot");
#if HOST_FCSR
    check(cpuFlags==1,"host flags publication");
    p=operation(0x003091f3,0);check(p[4] && p[9]==2 && !p[13] && cpuFlags==1,"misrouted host FCSR CSR accepted");
#else
    check(status()[6]==1,"standalone flags publication");
#endif
    ++commands;
#else
    p=operation(0x030c1457);check(p[4] && p[8] && p[9]==2 && p[10]==0x030c1457,"integer FP rejection");
#endif
    check(requests==responses && !pending && !dvalid,"final bus drain");
    std::cout<<"PASS isolated directed stop_before_issue=1 stop_preview=1 grant_stop=1 load_stop=1 store_stop=1 prefix_retry=2 denied=1 monitor=1 monitor_burst=1 monitor_control=1 fp_or_reject=1 hardware="<<hardware<<" requests="<<requests<<" responses="<<responses<<'\n';
  }
};
int main(int argc,char**argv){try{
  Driver d;if(argc==2 && std::string(argv[1])!="--directed")d.negative=argv[1];d.reset();
  if(argc==2 && std::string(argv[1])=="--directed"){d.directed();return 0;}
  std::array<uint64_t,64> expected{};std::string line;
  while(std::getline(std::cin,line)){
    std::istringstream in(line);std::string kind;in>>kind;
    if(kind=="R"){unsigned r;std::string bits;in>>r>>bits;d.check(r<32 && bits.size()==32,"RF fixture");d.context(2*r,true,std::stoull(bits.substr(16),nullptr,16));d.context(2*r+1,true,std::stoull(bits.substr(0,16),nullptr,16));}
    else if(kind=="E"){for(auto& word:expected)d.check(bool(in>>std::hex>>word),"expected RF fixture");}
    else if(kind=="I")d.command(line.substr(2),expected);
    else if(kind=="M"){std::string bits;in>>bits;d.check(bits.size()==2*d.ram.size() && !d.pending && !d.dvalid,"RAM initialization");for(unsigned i=0;i<d.ram.size();i++)d.ram[i]=std::stoul(bits.substr(2*i,2),nullptr,16);}
    else if(kind=="F"){d.check(!d.pending && !d.dvalid,"fault setup while pending");d.check(bool(in>>std::hex>>d.faultAddress>>d.faultLength),"fault fixture");}
    else d.check(false,"unknown fixture event");
  }
  d.check(d.commands>0,"empty fixture");
  std::cout<<"PASS isolated public DUT commands="<<d.commands<<" hardware="<<d.hardware<<" host_csr="<<d.local<<" cycles="<<d.cycles<<" reads="<<d.reads<<" requests="<<d.requests<<" responses="<<d.responses<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
