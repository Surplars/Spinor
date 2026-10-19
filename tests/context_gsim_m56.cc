// Public-port integration of the portable C image API. DUT expectations are
// independent Python byte images, never a second call to the C serializer.
#define main spinor_differential_driver_main
#include "m56_host_driver.cc"
#undef main
#include "spinor_context.h"
#include <algorithm>
#include <cstring>
#include <limits>
using Image=std::array<uint8_t,SPINOR_CONTEXT_BYTES>;
struct ContextHarness:Driver {
  bool owned=false,poisoned=false,external_busy=false,wrong_geometry=false;
  unsigned callbacks=0,begins=0,ends=0,fail_at=UINT32_MAX;
  bool negative_unlock=false,negative_skip_start=false,fail_after=false;
  spinor_context_ops ops{};
  ContextHarness(){
    ops.opaque=this;ops.features=ENABLE_FP?SPINOR_CONTEXT_FP:0;
    ops.acquire=[](void* p,int restoring){auto& h=*(ContextHarness*)p;++h.begins;
      if(h.external_busy || h.pending || h.dvalid || h.dut.get_io$$core$$busy() || h.dut.get_io$$core$$completion$$valid() || (h.owned && !(h.poisoned && restoring)))return -1;
      h.owned=true;h.callbacks=0;return 0;};
    ops.release=[](void*p,int valid){auto& h=*(ContextHarness*)p;++h.ends;
      h.check(h.owned,"release without lease");
      if(valid || h.negative_unlock){h.owned=false;h.poisoned=false;}else{h.poisoned=true;}};
    ops.read_chunk=[](void*p,uint32_t address,uint64_t*data){auto&h=*(ContextHarness*)p;
      h.check(h.owned && address<64,"unleased context read");const bool fail=h.callbacks++==h.fail_at;if(fail && !h.fail_after)return -1;
      *data=h.context(address,false,0);return fail?-1:0;};
    ops.write_chunk=[](void*p,uint32_t address,uint64_t data){auto&h=*(ContextHarness*)p;
      h.check(h.owned && address<64,"unleased context write");const bool fail=h.callbacks++==h.fail_at;if(fail && !h.fail_after)return -1;
      h.context(address,true,data);return fail?-1:0;};
    ops.execute=[](void*p,uint32_t raw,uint64_t scalar,uint64_t scalar2,uint64_t avl,uint64_t*result){auto&h=*(ContextHarness*)p;
      h.check(h.owned,"unleased command");const bool fail=h.callbacks++==h.fail_at;if(fail && !h.fail_after)return -1;
      if(h.negative_skip_start && raw>>20==8 && (raw>>12&3)==1){*result=0;return 0;}
      *result=h.issue(raw,scalar,scalar2,avl);
      if(h.wrong_geometry && raw>>20==0xc22)*result=32;
      return fail?-1:0;};
  }
  struct Reply{bool illegal=false,fault=false,interrupted=false;uint64_t cause=0,address=0,element=0;} reply;
  unsigned busy_probes=0;
  uint64_t issue(uint32_t raw,uint64_t scalar=0,uint64_t scalar2=0,uint64_t avl=0,bool probe=false){
    if((raw&127)==0x73 && (raw>>20)>=1 && (raw>>20)<=3) {
      // Model the CPU's unique CSR owner; no FCSR CSR reaches VPU command.
      const unsigned address=raw>>20,action=raw>>12&3,rs1=raw>>15&31;
      const uint64_t old=address==1?hostFlags:address==2?hostFrm:(hostFrm<<5)|hostFlags;
      const uint64_t source=raw&(1u<<14)?rs1:scalar;
      const bool write=action==1 || (rs1 && action);
      if(write){
        const auto value=action==1?source:action==2?old|source:old&~source;
        host(address==1?hostFrm:address==2?value&7:(value>>5)&7,address==2?hostFlags:value&31);
      }
      tick();++commands;return old;
    }
    const Wide token=(Wide(0x53ce)<<64)|commands;const auto started=cycles;
    dut.set_io$$core$$command$$bits$$instruction(raw);dut.set_io$$core$$command$$bits$$scalar(scalar);dut.set_io$$core$$command$$bits$$scalar2(scalar2);dut.set_io$$core$$command$$bits$$avl(avl);dut.set_io$$core$$command$$bits$$token(token);
    dut.set_io$$core$$command$$valid(1);tick();check(dut.get_io$$core$$command$$ready(),"context command blocked");dut.set_io$$core$$command$$valid(0);
    bool probed=false;
    for(;;){
      tick();check(cycles-started<200000,"context command timeout");
      if(probe && !probed && pending){
        Image forbidden{};const auto before=callbacks;const auto req=requests;
        check(spinor_context_save(&ops,forbidden.data(),forbidden.size())==SPINOR_CTX_BUSY,"active-memory lease admitted");
        check(callbacks==before && requests==req && !owned,"busy save touched active instruction");probed=true;++busy_probes;
      }
      if(dut.get_io$$core$$completion$$valid())break;
    }
    const auto result=dut.get_io$$core$$completion$$bits$$scalar();const auto held=architecture();const auto status=memory_status();
    for(unsigned i=0;i<commands%4+1;i++){
      check(dut.get_io$$core$$completion$$bits$$token()==token && dut.get_io$$core$$completion$$bits$$instruction()==raw,"context completion identity");
      check(architecture()==held && memory_status()==status && dut.get_io$$core$$completion$$bits$$scalar()==result,"context completion unstable");tick();
    }
    reply={bool(dut.get_io$$core$$completion$$bits$$illegal()),bool(dut.get_io$$memoryStatus$$bits$$fault()),bool(dut.get_io$$memoryStatus$$bits$$interrupted()),dut.get_io$$memoryStatus$$bits$$cause(),dut.get_io$$memoryStatus$$bits$$address(),dut.get_io$$memoryStatus$$bits$$element()};
    check(!reply.illegal,"context operation illegal");check(!pending && !dvalid,"context completion before drain");
    ready(1);tick();ready(0);tick();++commands;
    if(probe)check(probed,"missing active-memory probe");return result;
  }
  void csr(unsigned address,uint64_t value){issue(address<<20|1<<15|1<<12|0x73,value);}
  bool cpu_admissible()const{return !owned && !poisoned;}
};
static std::vector<uint8_t> bytes(const std::string& path){
  std::ifstream f(path,std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("fixture open "+path);
  auto n=f.tellg();if(n<0)throw std::runtime_error("fixture size");std::vector<uint8_t> out((size_t)n);f.seekg(0);f.read((char*)out.data(),n);if(!f)throw std::runtime_error("fixture read");return out;
}
static void compare_image(ContextHarness&h,const Image&got,const std::string&path){
  const auto expected=bytes(path);h.check(expected.size()==got.size() && std::equal(got.begin(),got.end(),expected.begin()),"independent image mismatch "+path);
}
int main(int argc,char**argv){try{
  if(argc<2 || argc>3)throw std::runtime_error("Usage: context-test cases [negative]");ContextHarness h;h.reset();
  if(argc==3){h.negative_unlock=std::string(argv[2])=="unlock-on-error";h.negative_skip_start=std::string(argv[2])=="skip-vstart";}
  std::ifstream input(argv[1]);if(!input)throw std::runtime_error("cases open");
  uint64_t id,type,vl,start,vcsr,fcsr,mode;std::string snapshot,resumed,ram_before,ram_after;
  unsigned tested=0,restore_failures=0,save_failures=0;uint64_t save_cycles=0,restore_cycles=0;Image recovery{};bool have_recovery=false;
  while(input>>std::hex>>id>>type>>vl>>start>>vcsr>>fcsr>>mode>>snapshot>>resumed>>ram_before>>ram_after){
    std::array<uint64_t,64> seed{};for(auto&word:seed)if(!(input>>std::hex>>word))throw std::runtime_error("case RF short");
    h.check(h.cpu_admissible(),"previous context owns CPU");
    for(unsigned k=0;k<64;k++)h.context(k,true,seed[k]);
    for(unsigned k=0;k<h.ram.size();k++)h.ram[k]=(k*13+7)&255;
    h.issue(0x8020f1d7,0,type,vl);h.csr(15,vcsr);
#if ENABLE_FP
    h.csr(3,fcsr);
#endif
    h.csr(8,start);
    uint32_t memory_raw=7|1<<25|1<<15|6<<12|8<<7;
    if(mode>=1 && mode<=3){
      if(mode==2)memory_raw|=2u<<29;if(mode==3)memory_raw|=0x20;
      h.fault_address=BASE+(mode==2?16:4);h.fault_length=4;
      h.issue(memory_raw,BASE,0,0,true);h.check(h.reply.fault && h.reply.cause==(mode==3?7u:5u) && h.reply.element==1 && h.reply.address==h.fault_address,"fault-prefix setup");h.fault_length=0;
    }
    Image saved{};auto begin=h.cycles;h.check(spinor_context_save(&h.ops,saved.data(),saved.size())==0,"save failed");save_cycles+=h.cycles-begin;
    h.check(h.cpu_admissible(),"save kept lease");compare_image(h,saved,snapshot);
    auto expected_ram=bytes(ram_before);h.check(expected_ram.size()==h.ram.size() && std::equal(h.ram.begin(),h.ram.end(),expected_ram.begin()),"pre-restore RAM mismatch");
    // Another task overwrites all VRF rows and CSR state; external task RAM is
    // deliberately retained, including any irrevocable store prefix.
    for(unsigned k=0;k<64;k++)h.context(k,true,~seed[k]);
    h.issue(0x8020f1d7,0,0,1);h.csr(15,7);
#if ENABLE_FP
    h.csr(3,0xff);
#endif
    h.csr(8,127);
    const auto trusted=bytes(snapshot);begin=h.cycles;h.check(spinor_context_restore(&h.ops,trusted.data(),trusted.size())==0,"restore failed");restore_cycles+=h.cycles-begin;
    h.check(h.cpu_admissible(),"restored context kept lease");Image verify{};h.check(spinor_context_save(&h.ops,verify.data(),verify.size())==0,"restored save failed");compare_image(h,verify,snapshot);
    if(mode>=1 && mode<=3)h.issue(memory_raw,BASE);
    else if(mode==4)h.issue(0x10u<<20|0x18u<<15|1u<<12|8u<<7|0x57);
    else if(mode==5)h.issue(0xac004057u|0x10u<<20|1u<<15|8u<<7,1);
    else if(!(type>>63))h.issue(0x10u<<20|1u<<15|4u<<12|8u<<7|0x57,17); // masked vadd.vx
    h.check(spinor_context_save(&h.ops,verify.data(),verify.size())==0,"continuation save failed");compare_image(h,verify,resumed);
    expected_ram=bytes(ram_after);h.check(expected_ram.size()==h.ram.size() && std::equal(h.ram.begin(),h.ram.end(),expected_ram.begin()),"continuation RAM mismatch");
    if(!have_recovery && vl>1 && start==1 && !mode){recovery=saved;have_recovery=true;}
    ++tested;
  }
  h.check(tested>0 && have_recovery,"empty context corpus");
  // Every low-level callback in restore/save gets an injected failure. A
  // failed operation retains the lease; a complete retry is the release point.
  const unsigned restore_ops=ENABLE_FP?69:68,save_ops=ENABLE_FP?70:69;
  for(unsigned phase=0;phase<2;phase++)for(unsigned fail=0;fail<restore_ops;fail++){
    h.fail_after=phase;
    h.fail_at=fail;const auto result=spinor_context_restore(&h.ops,recovery.data(),recovery.size());
    h.check(result==SPINOR_CTX_IO && h.owned && h.poisoned && !h.cpu_admissible(),"failed restore released ownership");
    Image blocked{};h.check(spinor_context_save(&h.ops,blocked.data(),blocked.size())==SPINOR_CTX_BUSY,"poisoned save admitted");
    h.fail_at=UINT32_MAX;h.check(spinor_context_restore(&h.ops,recovery.data(),recovery.size())==0,"restore retry failed");
    Image verify{};h.check(spinor_context_save(&h.ops,verify.data(),verify.size())==0 && verify==recovery,"retry state differs");++restore_failures;
  }
  for(unsigned phase=0;phase<2;phase++)for(unsigned fail=0;fail<save_ops;fail++){
    h.fail_after=phase;
    h.fail_at=fail;Image bad{};const auto result=spinor_context_save(&h.ops,bad.data(),bad.size());
    h.check(result==SPINOR_CTX_IO && h.owned && h.poisoned && !h.cpu_admissible(),"failed save released ownership");
    h.check(spinor_context_validate(bad.data(),bad.size(),h.ops.features)!=0,"failed save left valid image");
    h.fail_at=UINT32_MAX;h.check(spinor_context_restore(&h.ops,recovery.data(),recovery.size())==0,"save-error recovery failed");++save_failures;
  }
  h.external_busy=true;Image busy{};auto count=h.commands;h.check(spinor_context_save(&h.ops,busy.data(),busy.size())==SPINOR_CTX_BUSY && h.commands==count,"busy save issued command");
  h.check(spinor_context_restore(&h.ops,recovery.data(),recovery.size())==SPINOR_CTX_BUSY && h.commands==count,"busy restore issued command");h.external_busy=false;
  h.wrong_geometry=true;h.check(spinor_context_restore(&h.ops,recovery.data(),recovery.size())==SPINOR_CTX_GEOMETRY && !h.cpu_admissible(),"target geometry guard");
  // A geometry error during a poisoned retry must not unlock prior partial
  // state. Invalid images must likewise preserve that recovery obligation.
  h.check(spinor_context_restore(&h.ops,recovery.data(),recovery.size())==SPINOR_CTX_GEOMETRY && h.owned && h.poisoned && !h.cpu_admissible(),"poisoned geometry retry unlocked");
  Image invalid=recovery;invalid[64]^=1;const auto begins=h.begins;
  h.check(spinor_context_restore(&h.ops,invalid.data(),invalid.size())==SPINOR_CTX_CHECKSUM && h.begins==begins && !h.cpu_admissible(),"invalid recovery touched lease");
  h.check(spinor_context_save(&h.ops,busy.data(),busy.size())==SPINOR_CTX_BUSY,"geometry-poisoned save admitted");
  h.wrong_geometry=false;h.check(spinor_context_restore(&h.ops,recovery.data(),recovery.size())==0 && h.cpu_admissible(),"geometry recovery failed");
  Image final_image{};h.check(spinor_context_save(&h.ops,final_image.data(),final_image.size())==0 && final_image==recovery,"geometry recovery state differs");
  std::cout<<"PASS context GSIM cases="<<tested<<" restore_failures="<<restore_failures<<" save_failures="<<save_failures<<" busy_memory="<<h.busy_probes<<" geometry_guards=2 save_cycles="<<save_cycles<<" restore_cycles="<<restore_cycles<<" total_cycles="<<h.cycles<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
