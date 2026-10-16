package com.xilinx.rapidwright.timing;

import com.xilinx.rapidwright.design.Design;
import com.xilinx.rapidwright.timing.*;
import org.jgrapht.alg.cycle.CycleDetector;
import java.lang.reflect.Field;

/** Structural/model experiment on an existing implementation, not signoff STA. */
public class CloudTimingAudit {
    public static void main(String[] args) throws Exception {
        Design d = Design.readCheckpoint(args[0]);
        TimingModel model = new TimingModel(d.getDevice());
        model.build();
        TimingGraph graph = new TimingGraph(d, null, null, args[1]);
        // In the pinned release the constructor can leave its private folder
        // field unset (parameter self-assignment). Check the actual value and
        // record a narrowly scoped compatibility workaround, without editing JARs.
        Field folder = TimingGraph.class.getDeclaredField("dspTimingDataFolder");
        folder.setAccessible(true);
        boolean folderWorkaround = !args[1].equals(folder.get(graph));
        if (folderWorkaround) folder.set(graph, args[1]);
        System.out.println("PROBE_FOLDER_WORKAROUND " + folderWorkaround);
        graph.setTimingModel(model);
        graph.build(false, d.getNets());
        System.out.println("PROBE_VERTICES " + graph.vertexSet().size());
        System.out.println("PROBE_EDGES " + graph.edgeSet().size());
        int dspEdges = 0;
        for (TimingEdge e : graph.edgeSet()) {
            if (e.getSrc().toString().contains("partials_p") &&
                e.getDst().toString().contains("partials_p") && e.getLogicDelay() > 0) dspEdges++;
        }
        System.out.println("PROBE_DSP_LOGIC_EDGES " + dspEdges);
        graph.removeClockCrossingPaths();
        graph.buildSuperGraphPaths();
        boolean cycles = new CycleDetector<>(graph).detectCycles();
        System.out.println("PROBE_CYCLES " + cycles);
        if (!cycles) {
            graph.computeArrivalTimesTopologicalOrder();
            if (args.length > 2) {
                var vertices = new java.util.HashMap<String, TimingVertex>();
                for (var v : graph.vertexSet()) vertices.put(v.toString(), v);
                var order = new java.util.ArrayList<TimingVertex>();
                var iterator = new org.jgrapht.traverse.TopologicalOrderIterator<TimingVertex, TimingEdge>(graph);
                while (iterator.hasNext()) order.add(iterator.next());
                var output = new java.util.ArrayList<String>();
                output.add("source\tendpoint\treference_ps\tstatus");
                for (String line : java.nio.file.Files.readAllLines(java.nio.file.Path.of(args[2]))) {
                    String[] pins = line.split("\t");
                    var start = vertices.get(pins[0]);
                    var end = vertices.get(pins[1]);
                    if (start == null || end == null) {
                        output.add(line + "\t\tMISSING_VERTEX"); continue;
                    }
                    var distance = new java.util.HashMap<TimingVertex, Float>();
                    distance.put(start, 0f);
                    for (var v : order) {
                        if (!distance.containsKey(v)) continue;
                        for (var e : graph.outgoingEdgesOf(v)) {
                            // Never join separate register paths through synthetic vertices.
                            if (e.getDst().toString().startsWith("super")) continue;
                            float candidate = distance.get(v) + e.getDelay();
                            distance.merge(e.getDst(), candidate, Math::max);
                        }
                    }
                    Float delay = distance.get(end);
                    output.add(line + "\t" + (delay == null ? "" : delay.toString()) +
                        "\t" + (delay == null ? "NO_PATH" : "MATCHED"));
                }
                java.nio.file.Files.write(java.nio.file.Path.of(args[3]), output);
            }
            var maximum = graph.getMaxDelay();
            System.out.println("PROBE_REFERENCE_PATH_PS " + maximum.getFirst());
            var edges = graph.getCriticalTimingEdgesInOrder(maximum.getSecond());
            var realEdges = edges.stream().filter(e ->
                !e.getSrc().toString().startsWith("super") &&
                !e.getDst().toString().startsWith("super")).toList();
            if (!realEdges.isEmpty()) {
                System.out.println("PROBE_REFERENCE_START " + realEdges.get(0).getSrc());
                System.out.println("PROBE_REFERENCE_END " + realEdges.get(realEdges.size()-1).getDst());
            }
        }
        System.out.println("PROBE_NO_CLOCK_TREE_HOLD_OR_SPEED_GRADE_SIGNOFF");
    }
}
