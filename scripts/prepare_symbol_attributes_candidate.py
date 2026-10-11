"""Prepare new exporter candidates, preserving every existing EL method."""
import re
from pathlib import Path
import shutil
import sys

BASE=Path(__file__).resolve().parents[1]
PRIOR=BASE/'.artifacts/GNET-MultiAssetReview-v45-r1'
ROOT=BASE/'.artifacts/GNET-SymbolAttributes-v46-r1'
BROKER='guarded-v46-symbol-attributes'
CLIENT='gnet-client-v79-symbol-attributes'

VARIABLES='''    SymbolAttributesProvider SymbolProvider(null),
    Timer SymbolTimer(null),
    intrabarpersist SymbolDone(false),
    intrabarpersist SymbolTimerCalls(0),
    intrabarpersist SymbolStatus("loading"),
    intrabarpersist SymbolReturned(""),
    intrabarpersist SymbolCountry(""),
    intrabarpersist SymbolExchange(""),
    intrabarpersist SymbolTypeName(""),
    intrabarpersist SymbolCapturedAt(""),
    intrabarpersist SymbolPointValue(0),
    intrabarpersist SymbolMinMove(0),
    intrabarpersist SymbolPriceScale(0),
    intrabarpersist SymbolDeliveryMonth(-1),
    intrabarpersist SymbolDeliveryYear(0),
    intrabarpersist SymbolChartPointValue(0),
'''

METHODS='''method string GnetSymbolAttributesText()
Vars: string Payload;
Begin
    Payload="{"+DoubleQuote+"schema_version"+DoubleQuote+":"+GnetJsonString("gnet-ts-symbol-attributes-1")
        +","+DoubleQuote+"status"+DoubleQuote+":"+GnetJsonString(SymbolStatus)
        +","+DoubleQuote+"requested_symbol"+DoubleQuote+":"+GnetJsonString(CapturedSymbol)
        +","+DoubleQuote+"provider_symbol"+DoubleQuote+":"+GnetJsonString(SymbolReturned)
        +","+DoubleQuote+"country_raw"+DoubleQuote+":"+GnetJsonString(SymbolCountry)
        +","+DoubleQuote+"exchange_raw"+DoubleQuote+":"+GnetJsonString(SymbolExchange)
        +","+DoubleQuote+"symbol_type"+DoubleQuote+":"+GnetJsonString(SymbolTypeName)
        +","+DoubleQuote+"point_value"+DoubleQuote+":"+NumToStr(SymbolPointValue,8)
        +","+DoubleQuote+"min_move"+DoubleQuote+":"+NumToStr(SymbolMinMove,8)
        +","+DoubleQuote+"price_scale"+DoubleQuote+":"+NumToStr(SymbolPriceScale,8)
        +","+DoubleQuote+"delivery_month"+DoubleQuote+":"+NumToStr(SymbolDeliveryMonth,0)
        +","+DoubleQuote+"delivery_year"+DoubleQuote+":"+NumToStr(SymbolDeliveryYear,0)
        +","+DoubleQuote+"chart_big_point_value"+DoubleQuote+":"+NumToStr(SymbolChartPointValue,8)
        +","+DoubleQuote+"captured_at_local"+DoubleQuote+":"+GnetJsonString(SymbolCapturedAt)
        +","+DoubleQuote+"realtime_updates"+DoubleQuote+":false}";
    Return "symbol_attributes_json="+Payload+NewLine;
End;

method void GnetCheckSymbolAttributes()
Begin
    If Not SymbolDone And Not AutoRemoved And SymbolProvider<>null Then Begin
        If SymbolProvider.State=tsdata.common.DataState.Failed Then Begin
            SymbolStatus="failed"; SymbolDone=true;
        End
        Else If SymbolProvider.State=tsdata.common.DataState.Loaded Then Begin
            try
                SymbolReturned=SymbolProvider.Symbol;
                SymbolCountry=SymbolProvider.Country;
                SymbolExchange=SymbolProvider.Exchange;
                SymbolTypeName=SymbolProvider.SymbolType.ToString();
                SymbolPointValue=SymbolProvider.PointValue;
                SymbolMinMove=SymbolProvider.MinMove;
                SymbolPriceScale=SymbolProvider.PriceScale;
                SymbolDeliveryMonth=SymbolProvider.DeliveryMonth;
                SymbolDeliveryYear=SymbolProvider.DeliveryYear;
                SymbolStatus="loaded";
                If SymbolReturned<>CapturedSymbol Or StrLen(SymbolCountry)=0
                    Or StrLen(SymbolExchange)=0 Or StrLen(SymbolTypeName)=0
                    Or SymbolPointValue<=0 Or SymbolMinMove<=0 Or SymbolPriceScale<=0 Then
                    SymbolStatus="incomplete";
            catch (elsystem.Exception ex)
                SymbolStatus="failed";
            end;
            SymbolDone=true;
        End;
        If SymbolDone Then Begin
            SymbolCapturedAt=DateTime.Now.Format("%Y-%m-%dT%H:%M:%S");
            If SymbolTimer<>null Then SymbolTimer.Stop();
            If SnapshotClosed And AutoProbeDone Then GnetCheckAutoProbe();
        End;
    End;
End;

method void GnetSymbolChanged(Object Sender, tsdata.common.StateChangedEventArgs Args)
Begin
    GnetCheckSymbolAttributes();
End;

method void GnetSymbolElapsed(Object Sender, TimerElapsedEventArgs Args)
Begin
    If Not AutoRemoved And Not SymbolDone Then Begin
        SymbolTimerCalls=SymbolTimerCalls+1; GnetCheckSymbolAttributes();
        If Not SymbolDone And SymbolTimerCalls>=30 Then Begin
            SymbolStatus="timeout"; SymbolDone=true;
            SymbolCapturedAt=DateTime.Now.Format("%Y-%m-%dT%H:%M:%S");
            SymbolTimer.Stop();
            If SnapshotClosed And AutoProbeDone Then GnetCheckAutoProbe();
        End;
    End;
End;

method void GnetStartSymbolAttributes()
Begin
    SymbolChartPointValue=BigPointValue;
    SymbolProvider=SymbolAttributesProvider.Create(); SymbolProvider.Load=false;
    SymbolProvider.Symbol=CapturedSymbol; SymbolProvider.Realtime=false;
    SymbolProvider.StateChanged += GnetSymbolChanged;
    SymbolTimer=Timer.Create(); SymbolTimer.Interval=1000; SymbolTimer.AutoReset=true;
    SymbolTimer.Elapsed += GnetSymbolElapsed;
    SymbolTimer.Start(); SymbolProvider.Load=true; GnetCheckSymbolAttributes();
End;

'''


def replace(text,old,new):
    if text.count(old)!=1:
        raise RuntimeError('Unexpected exporter anchor: '+old)
    return text.replace(old,new)


def main():
    if sys.argv[1:] != ['--resume']:
        if ROOT.exists():
            raise RuntimeError('Preserve existing candidate')
        ROOT.mkdir()
        shutil.copytree(PRIOR/'guarded-v45-multi-asset-review',ROOT/BROKER,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(PRIOR/'gnet-client-v78-multi-asset-review',ROOT/CLIENT,ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('GNET_Bar_Export.els','GNET_Primary_Research_Export.els','GNET_Primary_Generic_Scaffold.els'):
        path=ROOT/CLIENT/'EL_files'/name
        text=path.read_text(encoding='utf-8')
        if 'method string GnetSymbolAttributesText()' in text:
            if sys.argv[1:] != ['--resume']:
                raise RuntimeError('Exporter already changed')
            continue
        prior=re.findall(r'^method\s+\w+\s+(\w+)\(',text,re.M)
        text=replace(text,'    Timer AutoTimer(null),','    Timer AutoTimer(null),\n'+VARIABLES)
        text=replace(text,'method void GnetPublishExport()',METHODS+'method void GnetPublishExport()')
        text=replace(text,'        + "chart_exchange=unknown" + NewLine','        + "chart_exchange=" + SymbolExchange + NewLine\n        + GnetSymbolAttributesText()')
        text=replace(text,'    If AutoTimer<>null Then AutoTimer.Stop();\n    If AutoProvider<>null Then AutoProvider.Load=false;',
            '    If AutoTimer<>null Then AutoTimer.Stop();\n    If AutoProvider<>null Then AutoProvider.Load=false;\n    If SymbolTimer<>null Then SymbolTimer.Stop();\n    If SymbolProvider<>null Then SymbolProvider.Load=false;')
        text=replace(text,'If AutoProbeDone And Not AutoRemoved And Not ExportFinished Then Begin',
            'If AutoProbeDone And SymbolDone And Not AutoRemoved And Not ExportFinished Then Begin')
        text=replace(text,'        Self.Uninitialized += GnetUninitialized;',
            '        Self.Uninitialized += GnetUninitialized;\n        GnetStartSymbolAttributes();')
        current=re.findall(r'^method\s+\w+\s+(\w+)\(',text,re.M)
        if [name for name in current if name in prior]!=prior or len(current)!=len(prior)+5:
            raise RuntimeError('Existing exporter methods changed')
        path.write_text(text,encoding='utf-8')
    print(ROOT)


if __name__=='__main__':
    main()
