/* Prototype Linux UIO client, not a vector execution/context-switch driver. */
#include "lishi_monitor.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>
static uint32_t rd(volatile uint32_t *p,unsigned offset)
{ uint32_t x=p[offset/4];__sync_synchronize();return x; }
static void wr(volatile uint32_t *p,unsigned offset,uint32_t x)
{ __sync_synchronize();p[offset/4]=x;__sync_synchronize(); }
static uint64_t rd64(volatile uint32_t *p,unsigned offset)
{ uint32_t lo=rd(p,offset);return (uint64_t)lo|((uint64_t)rd(p,offset+4)<<32); }
int main(int argc,char **argv)
{
 int existing=argc==3 && strcmp(argv[1],"--read-snapshot")==0;
 if((!existing && argc!=2) || (argc==3 && !existing)) {
  fprintf(stderr,"usage: %s [--read-snapshot] /dev/uioN\n",argv[0]);return 2;
 }
 int fd=open(argv[existing?2:1],O_RDWR|O_SYNC);
 if(fd<0){perror("open monitor");return 1;}
 if(flock(fd,LOCK_EX)<0){perror("lock monitor");close(fd);return 1;}
 volatile uint32_t *p=mmap(NULL,LISHI_MONITOR_MAP_BYTES,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
 if(p==MAP_FAILED){perror("mmap monitor");close(fd);return 1;}
 int rc=1;
 if(rd(p,LISHI_ID)!=LISHI_MONITOR_MAGIC || rd(p,LISHI_ABI)>>16!=LISHI_MONITOR_ABI_MAJOR || rd(p,LISHI_COUNTER_BITS)!=32) {
  fprintf(stderr,"unsupported monitor ID, ABI or counter width\n");goto out;
 }
 uint32_t previous=rd(p,LISHI_SEQUENCE);
 if(!existing)wr(p,LISHI_CONTROL,LISHI_SNAPSHOT);
 uint32_t sequence=rd(p,LISHI_SEQUENCE);
 if(!(rd(p,LISHI_STATUS)&LISHI_SNAPSHOT_VALID) || (!existing && sequence!=(uint32_t)(previous+1))) {
  fprintf(stderr,"snapshot acknowledgement missing\n");goto out;
 }
 uint32_t counters[LISHI_COUNTER_COUNT];
 for(unsigned i=0;i<LISHI_COUNTER_COUNT;i++)counters[i]=rd(p,LISHI_COUNTER_BASE+8*i);
 uint64_t status=rd64(p,LISHI_SNAPSHOT_STATUS),vtype=rd64(p,LISHI_SNAPSHOT_VTYPE);
 uint32_t config=rd(p,LISHI_SNAPSHOT_CONFIG),error=rd(p,LISHI_SNAPSHOT_ERROR);
 uint64_t address=rd64(p,LISHI_SNAPSHOT_ADDRESS),token=rd64(p,LISHI_SNAPSHOT_TOKEN_LO);
 uint32_t token_hi=rd(p,LISHI_SNAPSHOT_TOKEN_HI);
 if(sequence!=rd(p,LISHI_SEQUENCE) || !(rd(p,LISHI_STATUS)&LISHI_SNAPSHOT_VALID)) {
  fprintf(stderr,"snapshot changed while reading; require exclusive monitor ownership\n");goto out;
 }
 uint32_t g=rd(p,LISHI_GEOMETRY),g_hi=rd(p,LISHI_GEOMETRY+4);
 printf("{\"abi_major\":1,\"implementation\":%"PRIu32",\"caps\":%"PRIu32
        ",\"vlen\":%u,\"elen\":%u,\"vector_registers\":%u,\"instruction_capacity\":%u,\"architectural_vrf_bytes\":%"PRIu32
        ",\"counter_bits\":32,\"sequence\":%"PRIu32",\"status\":%"PRIu64",\"vtype\":%"PRIu64",\"config\":%"PRIu32
        ",\"error\":%"PRIu32",\"error_address\":%"PRIu64",\"error_token_lo\":%"PRIu64",\"error_token_hi\":%"PRIu32",\"counters\":{",
        rd(p,LISHI_IMPL),rd(p,LISHI_CAPS),g&65535,g>>16,g_hi&65535,g_hi>>16,rd(p,LISHI_CAPACITY),sequence,status,vtype,config,error,address,token,token_hi);
 static const char *names[LISHI_COUNTER_COUNT]={"cycles","busy_cycles","memory_owned_cycles","accepted","completed","canceled","illegal","memory_fault","memory_stop","tl_a","tl_d","command_stall","completion_stall"};
 for(unsigned i=0;i<LISHI_COUNTER_COUNT;i++)printf("%s\"%s\":%"PRIu32,i?",":"",names[i],counters[i]);
 puts("}}");rc=0;
out:
 munmap((void *)p,LISHI_MONITOR_MAP_BYTES);close(fd);return rc;
}
