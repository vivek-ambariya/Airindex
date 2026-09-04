/**
 * The wireframe frame from the mockups: square corners, hairline
 * border, four "+" registration marks. Transparent — these are line
 * drawings, not filled cards.
 */
export default function Blueprint({ as: Tag = "div", className = "", children, ...rest }) {
  return (
    <Tag className={`bp ${className}`} {...rest}>
      <i className="corner tl" aria-hidden="true" />
      <i className="corner tr" aria-hidden="true" />
      <i className="corner bl" aria-hidden="true" />
      <i className="corner br" aria-hidden="true" />
      {children}
    </Tag>
  )
}
