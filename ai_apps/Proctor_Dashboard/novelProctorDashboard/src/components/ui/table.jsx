import * as React from 'react';

// shadcn UI Table components (minimal implementation)

export const Table = ({ className, children, ...props }) => (
  <div className="w-full overflow-x-auto">
    <table className={`w-full border-collapse text-sm text-left ${className || ''}`} {...props}>
      {children}
    </table>
  </div>
);

export const TableHeader = ({ className, children, ...props }) => (
  <thead className={`bg-gray-800/50 ${className || ''}`} {...props}>
    {children}
  </thead>
);

export const TableBody = ({ className, children, ...props }) => (
  <tbody className={`divide-y divide-gray-700 ${className || ''}`} {...props}>
    {children}
  </tbody>
);

export const TableRow = ({ className, children, ...props }) => (
  <tr className={`${className || ''}`} {...props}>
    {children}
  </tr>
);

export const TableHead = ({ className, children, ...props }) => (
  <th className={`px-4 py-2 font-medium ${className || ''}`} {...props}>
    {children}
  </th>
);

export const TableCell = ({ className, children, ...props }) => (
  <td className={`px-4 py-2 ${className || ''}`} {...props}>
    {children}
  </td>
);

