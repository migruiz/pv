interface Props {
  gridKw: number;
  importing: boolean;
}

export function GridDisplay({ gridKw, importing }: Props) {
  return (
    <div className="grid-display">
      <div className="grid-value">{gridKw.toFixed(2)} kW</div>
      <div className={`grid-direction ${importing ? "importing" : "exporting"}`}>
        {importing ? "IMPORTING" : "EXPORTING"}
      </div>
    </div>
  );
}
