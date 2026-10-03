package dev.crosstesseract.core;

/** Passive finite reservoirs. Heat is microjoules in persistence; residuals never become free energy. */
public final class HeatModel {
    public record Exchange(long microjoules,double residual) {}
    public static Exchange exchange(double hotTemperature,double hotCapacity,double coldTemperature,double coldCapacity,
                                    double inverseConduction,double fraction,double residual,long maxMicrojoules) {
        for(double x:new double[]{hotTemperature,hotCapacity,coldTemperature,coldCapacity,inverseConduction,fraction,residual}) DomainException.require(Double.isFinite(x),"invalid_heat");
        DomainException.require(hotTemperature>=0 && coldTemperature>=0 && hotCapacity>=1 && coldCapacity>=1 && inverseConduction>=1 && fraction>0 && fraction<=0.25 && residual>=0 && residual<1 && maxMicrojoules>=0,"invalid_heat");
        if(hotTemperature<=coldTemperature) return new Exchange(0,residual);
        double equilibrium=(hotTemperature-coldTemperature)/(1/hotCapacity+1/coldCapacity);
        double exact=equilibrium*fraction/inverseConduction*1_000_000+residual;
        DomainException.require(Double.isFinite(exact) && exact>=0 && exact<Long.MAX_VALUE,"quantity_overflow");
        long whole=(long)exact,limited=Math.min(whole,maxMicrojoules);
        return new Exchange(limited,limited==whole?exact-whole:0);
    }
    private HeatModel() {}
}
