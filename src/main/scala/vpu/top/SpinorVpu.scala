package vpu

/** Public direct interface for a same-clock host and physical RAM fabric.
  *
  * VpuHostBoundary qualifies irrevocable CPU work and couples the final core
  * completion handshake to host retirement. Context access requires exclusive
  * ownership after instruction and memory traffic have drained. The monitor
  * is a separate MMIO slave; it does not submit work or arbitrate ownership.
  *
  * Use SpinorIsolated when the integration requires registered interface paths
  * and its preview/grant/done protocol. Internal Lishi/RamVector class names
  * preserve compatibility with existing generators and verification fixtures.
  */
class SpinorVpu(monitorBase:BigInt=0,config:SpinorParams=SpinorParams(),retimeMemory:Boolean=false) extends LishiVpuMonitored(monitorBase,config,retimeMemory) {
  override def desiredName="SpinorVpu"
}
