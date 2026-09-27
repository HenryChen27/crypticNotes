package com.crypticnotes.mobile;
import java.io.*;
import java.nio.file.*;

/** Actual phone screenshot grids plus translated viewport cases. Run through replay_frames.py. */
public class FrameEvidenceReplay {
    static int[] read(Path path) throws Exception {
        int[] pixels=new int[160*90];
        try(DataInputStream in=new DataInputStream(Files.newInputStream(path))) {
            for(int i=0;i<pixels.length;i++) pixels[i]=in.readInt();
        }
        return pixels;
    }
    static int viewport(int[] a,int[] b) { return FrameEvidence.changes(a,b,66,11,138,78,60,-1,-1,-1,-1); }
    public static void main(String[] args) throws Exception {
        Path root=Paths.get(args[0]); int checks=0;
        for(int i=0;i<3;i++) {
            int[] open=read(root.resolve("open-"+i+".bin"));
            if(viewport(open,open)!=0) throw new AssertionError("Static image changed"); checks++;
            for(int j=0;j<3;j++) {
                int[] closed=read(root.resolve("closed-"+j+".bin"));
                int controls=FrameEvidence.changes(open,closed,140,2,155,88,75,-1,-1,-1,-1);
                if(controls<24) throw new AssertionError("Missed close: "+i+" -> "+j+" "+controls);
                checks++;
            }
            int[] shifted=open.clone();
            for(int y=11;y<78;y++) for(int x=66;x<138;x++) shifted[y*160+x]=open[y*160+x-4];
            if(viewport(open,shifted)<60) throw new AssertionError("Missed pan "+i); checks++;
            int[] badge=open.clone();
            for(int y=20;y<=30;y++) for(int x=90;x<=110;x++) badge[y*160+x]=0xffffff;
            if(FrameEvidence.changes(open,badge,66,11,138,78,60,90,20,110,30)!=0)
                throw new AssertionError("Badge contaminated evidence"); checks++;
        }
        System.out.println("PASS "+checks+" frame checks: unchanged, closed, pan, badge exclusion");
    }
}
