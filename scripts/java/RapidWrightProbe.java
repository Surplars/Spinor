package com.xilinx.rapidwright.timing;

import com.xilinx.rapidwright.device.Part;
import com.xilinx.rapidwright.device.PartNameTools;
import com.xilinx.rapidwright.device.Device;

/** Capability probe. Family delay lookups are NOT a placed design or speed signoff. */
public class RapidWrightProbe {
    public static void main(String[] args) {
        Part p = PartNameTools.getPart("xczu15eg-ffvb1156-2-i");
        if (p == null) throw new IllegalStateException("Target part is absent");
        System.out.println("PART " + p.getName() + " " + p.getDevice() + " " + p.getSpeed() + " " + p.getSeries());
        DelayModel m = DelayModelBuilder.getDelayModel("ultrascaleplus");
        for (int i=1; i<=6; i++)
            System.out.println("ARC_PS A6LUT A" + i + " O6 " + m.getLogicDelay(m.getBELIndex("A6LUT"),"A"+i,"O6"));
        System.out.println("ARC_PS AFF CLK Q " + m.getLogicDelay(m.getBELIndex("AFF"),"CLK","Q"));
        System.out.println("NO_PLACEMENT_NO_ROUTING_NO_SPEED_GRADE_CALIBRATION");
        if (args.length > 0 && args[0].equals("--device")) {
            Device d=Device.getDevice(p.getDevice());
            if (d == null) throw new IllegalStateException("Target device database unavailable");
            System.out.println("DEVICE " + d.getName() + " rows=" + d.getRows() + " cols=" + d.getColumns());
        }
    }
}
