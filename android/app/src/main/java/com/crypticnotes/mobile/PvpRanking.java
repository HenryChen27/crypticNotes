package com.crypticnotes.mobile;

import java.util.ArrayList;
import java.util.List;

/**
 * Orders the hunters for the picker. Pure logic (android/tests/PvpRankingTest.java).
 *
 * The server answers with whatever hunters it has an opinion on; the picker
 * still has to offer every hunter, because the one the player actually met may
 * be one the model thought unlikely or did not know.
 */
final class PvpRanking {
    static final class Guess {
        final String name;final double probability;
        Guess(String name,double probability){this.name=name;this.probability=probability;}
    }

    /**
     * Every roster hunter exactly once: the server's, most likely first, then
     * the rest in roster order with probability 0. Names are compared without
     * the quotes some carry; names the roster does not know are dropped, as are
     * repeats and probabilities that are not numbers in [0, 1].
     */
    static List<Guess> order(String[] roster,List<String> names,List<Double> probabilities){
        List<Guess> ranked=new ArrayList<>();
        boolean[] used=new boolean[roster.length];
        for(int i=0;i<names.size();i++){
            int at=indexOf(roster,names.get(i));
            double p=i<probabilities.size() && probabilities.get(i)!=null?probabilities.get(i):0;
            if(at<0 || used[at] || Double.isNaN(p))continue;
            used[at]=true;
            ranked.add(new Guess(roster[at],Math.max(0,Math.min(1,p))));
        }
        ranked.sort((a,b)->Double.compare(b.probability,a.probability));   // stable: ties keep the server's order
        for(int i=0;i<roster.length;i++)if(!used[i])ranked.add(new Guess(roster[i],0));
        return ranked;
    }

    /**
     * The rows of the in-game list: the leading guesses that carry a number,
     * at most `limit` of them (0 = no limit). `ranked` is what order() returned.
     */
    static List<Guess> leading(List<Guess> ranked,int limit){
        List<Guess> out=new ArrayList<>();
        for(Guess guess:ranked){
            if(guess.probability<=0 || (limit>0 && out.size()>=limit))break;
            out.add(guess);
        }
        return out;
    }

    /** The same guesses in the roster's own order (the order the characters came out in), for picking by hand. */
    static List<Guess> byRoster(String[] roster,List<Guess> ranked){
        List<Guess> out=new ArrayList<>(ranked);
        out.sort((a,b)->Integer.compare(indexOf(roster,a.name),indexOf(roster,b.name)));
        return out;
    }

    static int indexOf(String[] roster,String name){
        String plain=PvpBanText.plain(name);
        for(int i=0;i<roster.length;i++)if(PvpBanText.plain(roster[i]).equals(plain))return i;
        return -1;
    }

    /** "21%", "<1%" for a non-zero chance that rounds to nothing, "" when the server said nothing. */
    static String percent(double probability){
        if(probability<=0)return "";
        long rounded=Math.round(probability*100);
        return rounded<1?"<1%":rounded+"%";
    }
}
