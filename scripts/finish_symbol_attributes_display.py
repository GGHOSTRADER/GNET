"""Finish bounded lookup failure handling and registered metadata presentation."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'.artifacts/GNET-SymbolAttributes-v46-r1'
CLIENT=ROOT/'gnet-client-v79-symbol-attributes'


def replace(path,old,new):
    text=path.read_text(encoding='utf-8')
    if text.count(old)!=1:raise RuntimeError('Final display anchor differs: '+path.name)
    path.write_text(text.replace(old,new),encoding='utf-8')


def main():
    old='''method void GnetStartSymbolAttributes()
Begin
    SymbolChartPointValue=BigPointValue;
    SymbolProvider=SymbolAttributesProvider.Create(); SymbolProvider.Load=false;
    SymbolProvider.Symbol=CapturedSymbol; SymbolProvider.Realtime=false;
    SymbolProvider.StateChanged += GnetSymbolChanged;
    SymbolTimer=Timer.Create(); SymbolTimer.Interval=1000; SymbolTimer.AutoReset=true;
    SymbolTimer.Elapsed += GnetSymbolElapsed;
    SymbolTimer.Start(); SymbolProvider.Load=true; GnetCheckSymbolAttributes();
End;'''
    new='''method void GnetStartSymbolAttributes()
Begin
    SymbolChartPointValue=BigPointValue;
    try
        SymbolProvider=SymbolAttributesProvider.Create(); SymbolProvider.Load=false;
        SymbolProvider.Symbol=CapturedSymbol; SymbolProvider.Realtime=false;
        SymbolProvider.StateChanged += GnetSymbolChanged;
        SymbolTimer=Timer.Create(); SymbolTimer.Interval=1000; SymbolTimer.AutoReset=true;
        SymbolTimer.Elapsed += GnetSymbolElapsed;
        SymbolTimer.Start(); SymbolProvider.Load=true; GnetCheckSymbolAttributes();
    catch (elsystem.Exception ex)
        SymbolStatus="failed"; SymbolDone=true;
        SymbolCapturedAt=DateTime.Now.Format("%Y-%m-%dT%H:%M:%S");
        If SymbolTimer<>null Then SymbolTimer.Stop();
    end;
End;'''
    for name in ('GNET_Bar_Export.els','GNET_Primary_Research_Export.els','GNET_Primary_Generic_Scaffold.els'):
        replace(CLIENT/'EL_files'/name,old,new)
    replace(CLIENT/'gnet_broker/data_preparation.html',"['Price basis',d.price_basis],",
        "['Price basis',d.price_basis],['Country',d.symbol_attributes?.country_raw||d.instrument_profile?.country||'Not recorded'],['Exchange',d.symbol_attributes?.exchange_raw||d.instrument_profile?.exchange||'Not recorded'],['Security type',d.symbol_attributes?.symbol_type||'Not recorded'],['Tick size',d.instrument_specification?.tick_size??'Not recorded'],['Point multiplier',d.instrument_specification?.multiplier??'Not recorded'],['Volume units',d.instrument_specification?.volume_units||'Not recorded'],")
    print('All three lookup constructors fail safely; registered metadata inspection enriched.')


if __name__=='__main__':
    main()
