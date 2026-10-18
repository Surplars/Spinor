#include "spinor_context.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned calls;
static void require(int ok, const char *message) { if (!ok) { fprintf(stderr,"%s\n",message); exit(1); } }
static int acquire(void *p, int restore) { (void)p; (void)restore; ++calls; return -1; }
static void release(void *p,int valid) { (void)p; (void)valid; ++calls; }
static int read_chunk(void *p,uint32_t a,uint64_t *v) { (void)p; (void)a; (void)v; ++calls; return -1; }
static int write_chunk(void *p,uint32_t a,uint64_t v) { (void)p; (void)a; (void)v; ++calls; return -1; }
static int execute(void *p,uint32_t i,uint64_t a,uint64_t b,uint64_t c,uint64_t *v) { (void)p; (void)i; (void)a; (void)b; (void)c; (void)v; ++calls; return -1; }
int main(int argc,char **argv) {
    require(argc==4,"Usage: validation valid-image bad-list fp");
    const unsigned fp=(unsigned)strtoul(argv[3],NULL,0);
    struct spinor_context_ops ops={NULL,fp,acquire,release,read_chunk,write_chunk,execute};
    unsigned char guarded[SPINOR_CONTEXT_BYTES+32],original[SPINOR_CONTEXT_BYTES];
    memset(guarded,0xa5,sizeof guarded);unsigned char *image=guarded+16;
    FILE *file=fopen(argv[1],"rb");require(file!=NULL,"fixture open");require(fread(image,1,SPINOR_CONTEXT_BYTES,file)==SPINOR_CONTEXT_BYTES,"fixture short");fclose(file);
    memcpy(original,image,sizeof original);require(spinor_context_validate(image,SPINOR_CONTEXT_BYTES,fp)==0,"valid Python frame rejected");
    unsigned bit_checks=0;
    for(unsigned i=0;i<SPINOR_CONTEXT_BYTES;i++)for(unsigned bit=0;bit<8;bit++) {
        image[i]^=(unsigned char)(1u<<bit);calls=0;
        require(spinor_context_validate(image,SPINOR_CONTEXT_BYTES,fp)!=0,"one-bit corruption accepted");
        require(spinor_context_restore(&ops,image,SPINOR_CONTEXT_BYTES)!=0 && calls==0,"bad frame touched device");
        image[i]^=(unsigned char)(1u<<bit);++bit_checks;
    }
    for(size_t n=0;n<SPINOR_CONTEXT_BYTES;n++) {
        calls=0;require(spinor_context_restore(&ops,image,n)==SPINOR_CTX_ARGUMENT && calls==0,"truncated frame touched device");
    }
    calls=0;require(spinor_context_restore(&ops,image,SPINOR_CONTEXT_BYTES+1)==SPINOR_CTX_ARGUMENT && calls==0,"oversized frame accepted");
    require(spinor_context_restore(&ops,NULL,SPINOR_CONTEXT_BYTES)==SPINOR_CTX_ARGUMENT,"null image accepted");
    require(spinor_context_restore(NULL,image,SPINOR_CONTEXT_BYTES)==SPINOR_CTX_ARGUMENT,"null ops accepted");
    struct spinor_context_ops missing=ops;missing.write_chunk=NULL;
    require(spinor_context_restore(&missing,image,SPINOR_CONTEXT_BYTES)==SPINOR_CTX_ARGUMENT,"missing callback accepted");
    require(!memcmp(image,original,sizeof original),"validation mutated source");
    for(unsigned i=0;i<16;i++)require(guarded[i]==0xa5 && guarded[SPINOR_CONTEXT_BYTES+16+i]==0xa5,"guard damaged");
    file=fopen(argv[2],"r");require(file!=NULL,"bad-list open");int expected;char path[512];unsigned metadata_checks=0;
    while(fscanf(file,"%d %511s",&expected,path)==2) {
        unsigned char bad[SPINOR_CONTEXT_BYTES];FILE *f=fopen(path,"rb");require(f!=NULL,"bad fixture open");require(fread(bad,1,sizeof bad,f)==sizeof bad,"bad fixture short");fclose(f);calls=0;
        require(spinor_context_validate(bad,sizeof bad,fp)==expected,"wrong malformed-header result");
        require(spinor_context_restore(&ops,bad,sizeof bad)==expected && calls==0,"malformed metadata touched device");++metadata_checks;
    }
    fclose(file);calls=0;
    require(spinor_context_restore(&ops,image,SPINOR_CONTEXT_BYTES)==SPINOR_CTX_BUSY && calls==1,"busy restore touched payload");
    unsigned char destination[SPINOR_CONTEXT_BYTES];memset(destination,0xff,sizeof destination);calls=0;
    require(spinor_context_save(&ops,destination,sizeof destination)==SPINOR_CTX_BUSY && calls==1,"busy save touched device");
    require(spinor_context_validate(destination,sizeof destination,fp)!=0,"busy save left valid image");
    printf("PASS context validation bit_flips=%u malformed_headers=%u truncated_sizes=%u\n",bit_checks,metadata_checks,SPINOR_CONTEXT_BYTES);
    return 0;
}
