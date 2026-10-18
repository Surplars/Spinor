// Physical RAM and fault transport for upstream Spike; no instruction semantics.
#include "processor.h"
#include "simif.h"
#include "encoding.h"
#include "mmu.h"
#include <array>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>

struct environment_t final : simif_t {
  cfg_t cfg;
  static constexpr uint64_t base=0x80010000;
  std::array<char,4096> code{};
  std::array<uint8_t,8192> ram{};
  uint64_t fault_address=0, fault_length=0;
  bool access_ok(uint64_t address,size_t length) {
    if(address<base || address-base>ram.size() || length>ram.size()-(address-base))return false;
    return !fault_length || !(address<fault_address+fault_length && fault_address<address+length);
  }
  std::map<size_t,processor_t*> harts;
  char* addr_to_mem(reg_t address) override {
    return address>=0x80000000 && address<0x80001000 ? code.data()+(address-0x80000000) : nullptr;
  }
  bool mmio_load(reg_t address,size_t length,uint8_t* data) override {
    if(!access_ok(address,length))return false;
    std::memcpy(data,ram.data()+address-base,length);return true;
  }
  bool mmio_store(reg_t address,size_t length,const uint8_t* data) override {
    if(!access_ok(address,length))return false;
    std::memcpy(ram.data()+address-base,data,length);return true;
  }
  void proc_reset(unsigned) override {}
  const cfg_t& get_cfg() const override { return cfg; }
  const std::map<size_t,processor_t*>& get_harts() const override { return harts; }
  const char* get_symbol(uint64_t) override { return nullptr; }
};

int main() {
  try {
    environment_t environment;
    processor_t cpu("rv64gcv_zvl128b","M",&environment.cfg,&environment,0,false,nullptr,std::cerr);
    environment.harts[0]=&cpu;
    cpu.enable_log_commits();
    auto reset=[&]() {
      cpu.reset();
      cpu.put_csr(CSR_MSTATUS,MSTATUS_VS|MSTATUS_FS);
      if(cpu.VU.VLEN!=128 || cpu.VU.ELEN!=64 || cpu.VU.vstart_alu)
        throw std::runtime_error("unexpected Spike vector configuration");
    };
    reset();
    std::string line;
    size_t id=0;
    while(std::getline(std::cin,line)) {
      std::istringstream in(line);std::string kind;in>>kind;
      if(kind.empty() || kind[0]=='#') continue;
      if(kind=="Z") { reset();continue; }
      if(kind=="M") {
        uint64_t offset;std::string data;
        if(!(in>>std::hex>>offset>>data) || data.size()%2 || offset>environment.ram.size() || data.size()/2>environment.ram.size()-offset)
          throw std::runtime_error("bad RAM fixture");
        for(size_t i=0;i<data.size()/2;i++)environment.ram[offset+i]=std::stoul(data.substr(2*i,2),nullptr,16);
        continue;
      }
      if(kind=="F") {
        if(!(in>>std::hex>>environment.fault_address>>environment.fault_length))throw std::runtime_error("bad fault range");
        continue;
      }
      if(kind=="R") {
        unsigned index;std::string data;in>>index>>data;
        if(index>=32 || data.size()!=32) throw std::runtime_error("bad register input");
        auto* row=static_cast<uint8_t*>(cpu.VU.reg_file)+16*index;
        for(unsigned i=0;i<16;i++) row[i]=std::stoul(data.substr(30-2*i,2),nullptr,16);
        continue;
      }
      if(kind!="I") throw std::runtime_error("unknown adapter command");
      uint32_t raw;uint64_t scalar,scalar2,avl;
      if(!(in>>std::hex>>raw>>scalar>>scalar2>>avl))throw std::runtime_error("bad instruction input");
      insn_t insn(raw);auto* state=cpu.get_state();
      if((raw&127)==0x57 && insn.funct3()==7) {
        state->XPR.write(insn.rs1(),avl);
        if(raw>>31==1 && raw>>30!=3)state->XPR.write(insn.rs2(),scalar2);
      } else if((raw&127)==0x57 && insn.funct3()==5) {
        state->FPR.write(insn.rs1(),freg_t{{scalar,~uint64_t(0)}});
      } else {
        state->XPR.write(insn.rs1(),scalar);
        if((raw&127)==7 || (raw&127)==0x27)state->XPR.write(insn.rs2(),scalar2);
      }
      state->serialized=true;
      state->log_reg_write.clear();state->log_mem_read.clear();state->log_mem_write.clear();
      bool trapped=false;uint64_t cause=0,tval=0;
      for(unsigned i=0;i<4;i++)environment.code[i]=raw>>(8*i);
      state->pc=0x80000000;
      try {
        auto fetched=cpu.get_mmu()->load_insn(state->pc);
        fetched.func(&cpu,fetched.insn,state->pc);
      }
      catch(trap_t& trap) { trapped=true;cause=trap.cause();tval=trap.get_tval(); }
      if(trapped && cause!=2 && cause!=4 && cause!=5 && cause!=6 && cause!=7)throw std::runtime_error("unexpected non-illegal trap");
      uint64_t result=0;bool writes=false;
      if(!trapped)for(const auto& [key,value]:state->log_reg_write) {
        const auto type=key&15;const auto index=key>>4;
        if((type==0 && index!=0) || type==1) {
          if(writes)throw std::runtime_error("multiple scalar results");
          writes=true;result=value.v[0];
        }
      }
      std::cout<<"S "<<std::dec<<id++<<' '<<trapped<<' '<<cause<<' '<<std::hex
               <<tval<<' '<<result<<' '<<writes<<' '<<cpu.get_csr(CSR_VL)<<' '<<cpu.get_csr(CSR_VTYPE)
               <<' '<<cpu.get_csr(CSR_VSTART)<<' '<<cpu.get_csr(CSR_VXRM)<<' '<<cpu.get_csr(CSR_VXSAT)
               <<' '<<cpu.get_csr(CSR_FRM)<<' '<<cpu.get_csr(CSR_FFLAGS);
      auto* regs=static_cast<uint8_t*>(cpu.VU.reg_file);
      for(unsigned r=0;r<32;r++) {
        std::cout<<' ';
        for(int byte=15;byte>=0;byte--)std::cout<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(regs[16*r+byte]);
      }
      std::cout<<'\n'<<"D "<<std::dec<<(id-1)<<' ';
      for(auto byte:environment.ram)std::cout<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(byte);
      std::cout<<'\n';
    }
    return 0;
  } catch(const std::exception& error) {
    std::cerr<<"Spike adapter failed: "<<error.what()<<'\n';return 1;
  }
}
