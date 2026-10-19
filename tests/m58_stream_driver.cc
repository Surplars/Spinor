// Test transport only: reuse the existing public-port command/RF/TL checker.
// Inline RF expectations avoid thousands of disk files; values are still
// produced exclusively by independent reference processes.
#define main previous_driver_main
#include "gsim_spike_driver.cc"
#undef main

int main(int argc,char**argv){try{
  if(argc<3 || argc>4)throw std::runtime_error("Usage: stream fixture|- scratch-rf-path [negative]");
  Driver d;if(argc==4)d.negative=argv[3];
  std::ifstream file;std::istream* input=&std::cin;
  if(std::string(argv[1])!="-"){file.open(argv[1]);d.check(bool(file),"stream fixture open");input=&file;}
  const std::string scratch=argv[2];d.reset();std::string line;bool expected=false;
  while(std::getline(*input,line)){
    std::istringstream in(line);std::string kind;in>>kind;
    if(kind.empty() || kind[0]=='#')continue;
    if(kind=="E"){
      std::ofstream golden(scratch);d.check(bool(golden),"inline RF scratch open");
      for(unsigned i=0;i<64;i++){uint64_t value;d.check(bool(in>>std::hex>>value),"short inline RF");golden<<std::hex<<value<<'\n';}
      std::string extra;d.check(!(in>>extra),"long inline RF");golden.close();d.check(bool(golden),"inline RF write");expected=true;
    }else if(kind=="I"){
      d.check(expected,"missing inline RF expectation");
      auto mark=line.find(" @ ");d.check(mark!=std::string::npos,"missing inline RF marker");
      line.replace(mark+1,1,scratch);std::istringstream command(line.substr(2));d.command(command);
    }else if(kind=="R"){
      unsigned reg;std::string bits;d.check(bool(in>>reg>>bits) && reg<32 && bits.size()==32,"bad stream RF write");
      d.context(2*reg,true,std::stoull(bits.substr(16),nullptr,16));d.context(2*reg+1,true,std::stoull(bits.substr(0,16),nullptr,16));
    }else if(kind=="M"){
      std::string bits;d.check(!d.pending && !d.dvalid && bool(in>>bits) && bits.size()==2*d.ram.size(),"bad stream RAM");
      for(unsigned k=0;k<d.ram.size();k++)d.ram[k]=std::stoul(bits.substr(2*k,2),nullptr,16);
    }else if(kind=="F")d.check(!d.pending && !d.dvalid && bool(in>>std::hex>>d.fault_address>>d.fault_length),"bad stream fault");
    else throw std::runtime_error("unknown stream event");
  }
  d.check(d.commands>0,"empty stream test");
  std::cout<<"PASS stream public DUT commands="<<d.commands<<" cycles="<<d.cycles<<" reads="<<d.reads<<" requests="<<d.requests<<" responses="<<d.responses<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
