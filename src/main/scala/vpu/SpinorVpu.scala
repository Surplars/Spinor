package vpu

/** Public SoC-facing VPU top for Valence / Orbital.
  * Same clock: irrevocable command/completion, context port, physical RAM TL
  * master, and a separate monitor TL slave. Pair with VpuHostBoundary at the
  * CPU retirement boundary. This is a partial RVV implementation, not a CPU.
  * Internal Lishi/RamVector names remain compatibility implementation details.
  */
class SpinorVpu(monitorBase:BigInt=0,config:SpinorParams=SpinorParams(),retimeMemory:Boolean=false) extends LishiVpuMonitored(monitorBase,config,retimeMemory) {
  override def desiredName="SpinorVpu"
}
